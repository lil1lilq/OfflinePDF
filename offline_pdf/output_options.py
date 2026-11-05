"""Optional final PDF size limits and conservative blank-page removal."""

from __future__ import annotations

import shutil
from decimal import Decimal, InvalidOperation

import pymupdf as pdf

from .engine import UserError, check_cancel, number, open_pdf, save_pdf

BLANK_MODE = "흰 빈 페이지 삭제"
SIZE_MODE = "목표 용량"


def size_limit(options, tool):
    key = "max_output_mb" if tool == "upscale" else "target_mb"
    if tool not in ("upscale", "compress") or (
        tool == "compress" and options.get("compression") != SIZE_MODE
    ):
        return None
    value = str(options.get(key, "")).strip()
    if not value and tool == "upscale":
        return None
    try:
        size = Decimal(value)
        if not size.is_finite() or not Decimal("0.01") <= size <= 100000:
            raise ValueError()
    except (InvalidOperation, ValueError):
        raise UserError("파일당 용량은 0.01~100000 MB 범위로 입력하세요.") from None
    return int(size * 1_000_000)


def validate_options(options, tool):
    mode = options.get("remove_blank", "사용 안 함")
    if mode not in ("사용 안 함", BLANK_MODE):
        raise UserError("빈 페이지 삭제 설정을 다시 선택하세요.")
    limit = size_limit(options, tool)
    if limit is not None:
        number(options.get("min_dpi", "96"), 72, 300, "최소 이미지 DPI", integer=True)
        number(options.get("min_quality", "50"), 30, 95, "최소 JPEG 품질", integer=True)
    return limit


def is_blank(page, cancel):
    """Only remove plain white pages without semantic or interactive objects.

    Check embedded images at their native resolution too: a tiny or faint mark
    must not disappear merely because the page preview was downsampled.
    Uninspectable / very large / transparent images are kept conservatively.
    """
    check_cancel(cancel)
    if (
        page.get_text("text").strip()
        or page.get_drawings()
        or page.get_links()
        or next(page.annots(), None) is not None
        or next(page.widgets(), None) is not None
    ):
        return False
    for info in page.get_image_info(xrefs=True):
        check_cancel(cancel)
        xref = info["xref"]
        if not xref or info["width"] * info["height"] > 16_000_000:
            return False
        if page.parent.xref_get_key(xref, "SMask")[0] != "null" or (
            page.parent.xref_get_key(xref, "Mask")[0] != "null"
        ):
            return False
        pix = pdf.Pixmap(page.parent, xref)
        if pix.alpha or pix.colorspace is None:
            return False
        if pix.colorspace != pdf.csRGB:
            pix = pdf.Pixmap(pdf.csRGB, pix)
        if min(pix.samples_mv, default=255) < 255:
            return False
    # Also cover content that is not represented by extractable text or images.
    if page.rect.width * page.rect.height * 4 > 16_000_000:
        return False
    pix = page.get_pixmap(matrix=pdf.Matrix(2, 2), colorspace=pdf.csRGB, alpha=False)
    return min(pix.samples_mv, default=255) == 255


def remove_blank_pages(doc, emit, cancel):
    blank = []
    for index in range(len(doc)):
        check_cancel(cancel)
        emit(
            {
                "type": "progress",
                "current": index,
                "total": len(doc),
                "label": "흰 빈 페이지 확인 중",
            }
        )
        if is_blank(doc[index], cancel):
            blank.append(index)
    if len(blank) == len(doc):
        raise UserError(
            "모든 결과 페이지가 빈 페이지입니다. 빈 페이지 삭제를 끄고 다시 실행하세요."
        )
    if blank:
        doc.delete_pages(blank)
    return len(blank)


def compression_trials(min_dpi, min_quality):
    """Start at high quality; each candidate is rebuilt from the same input."""
    dpis = sorted(
        {min_dpi, *(d for d in (600, 450, 300, 200, 150, 120, 96, 72) if d >= min_dpi)},
        reverse=True,
    )
    qualities = sorted(
        {min_quality, *(q for q in (95, 85, 75, 65, 50, 40, 30) if q >= min_quality)}, reverse=True
    )
    for dpi in dpis:
        for quality in qualities:
            yield dpi, quality


def fit_size(target, password, limit, options, work, emit, cancel):
    if target.stat().st_size <= limit:
        return False
    min_dpi = number(options.get("min_dpi", "96"), 72, 300, "최소 이미지 DPI", integer=True)
    min_quality = number(options.get("min_quality", "50"), 30, 95, "최소 JPEG 품질", integer=True)
    trials = list(compression_trials(min_dpi, min_quality))
    candidate = work / "candidate.pdf"
    smallest = target.stat().st_size
    for index, (dpi, quality) in enumerate(trials):
        check_cancel(cancel)
        emit(
            {
                "type": "progress",
                "current": index,
                "total": len(trials),
                "label": f"용량 맞추기 · {dpi} DPI / 품질 {quality}",
            }
        )
        # Reopening prevents repeated JPEG degradation and retains text/vectors.
        with open_pdf(target, password)[0] as doc:
            doc.rewrite_images(
                dpi_threshold=dpi + 1, dpi_target=dpi, quality=quality, bitonal=False
            )
            check_cancel(cancel)
            save_pdf(doc, candidate, password)
        size = candidate.stat().st_size
        smallest = min(smallest, size)
        if size <= limit:
            candidate.replace(target)
            return True
        candidate.unlink()
    raise UserError(
        f"설정한 {limit / 1_000_000:g} MB 이내로 저장할 수 없습니다. "
        f"시도한 최소 용량은 {smallest / 1_000_000:.3f} MB입니다. "
        "목표 용량을 늘리거나 최소 DPI·품질을 낮추세요. 이번 작업의 결과는 저장하지 않았습니다."
    )


def finalize_outputs(job, paths, stage, emit, cancel):
    options = job.get("options", {})
    if options.get("preview_only") or job["tool"] in ("text", "pdf_images"):
        return
    limit = validate_options(options, job["tool"])
    remove = options.get("remove_blank") == BLANK_MODE
    if not remove and limit is None:
        return
    work = stage / ".output-work"
    work.mkdir()
    removed = limited = 0
    try:
        for target in sorted(stage.glob("*.pdf")):
            check_cancel(cancel)
            if job["tool"] == "unlock":
                password = ""
            else:
                index = (
                    0
                    if job["tool"] in ("merge", "images_pdf")
                    else int(target.name.split("_", 1)[0]) - 1
                )
                # Generated input PDFs have no inherited password.
                inherited = job.get("passwords", {}).get(
                    str(paths[index]), options.get("input_password", "")
                )
                if job["tool"] in ("merge", "images_pdf"):
                    inherited = next((p for p in job.get("passwords", {}).values() if p), inherited)
                password = options.get("output_password") or inherited
            if remove:
                with open_pdf(target, password)[0] as doc:
                    count = remove_blank_pages(doc, emit, cancel)
                    if count:
                        replacement = work / "without-blanks.pdf"
                        save_pdf(doc, replacement, password)
                if count:
                    replacement.replace(target)
                    removed += count
            if limit is not None:
                limited += int(fit_size(target, password, limit, options, work, emit, cancel))
        emit(
            {
                "type": "output_summary",
                "removed_blank_pages": removed,
                "blank_enabled": remove,
                "size_checked": limit is not None,
                "compressed_files": limited,
            }
        )
    finally:
        shutil.rmtree(work)
