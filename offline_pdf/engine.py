"""Local-only PDF operations. No GUI, network, telemetry, or persistent history."""

from __future__ import annotations

import os
import re
import shutil
import socket
import uuid
from datetime import datetime
from pathlib import Path

import pymupdf as pdf

from .images import (
    EXPORT_FORMATS,
    IMAGE_EXTENSIONS,
    ImageReadError,
    iter_frames,
    png_bytes,
    save_pixmap,
)
from .ocr import OCRSetupError, model_directory
from .overlays import OverlayError, prepare_overlay


class UserError(Exception):
    pass


class Cancelled(Exception):
    pass


def disable_network():
    """Deny sockets in app and multiprocessing workers (defence in depth)."""

    def denied(*args, **kwargs):
        raise PermissionError("이 프로그램은 네트워크를 사용하지 않습니다.")

    socket.socket = denied
    socket.create_connection = denied
    socket.getaddrinfo = denied


def check_cancel(event):
    if event is not None and event.is_set():
        raise Cancelled()


def check_local_path(path):
    path = Path(path).expanduser()
    if str(path).startswith(("\\\\", "//")):
        raise UserError("네트워크 경로 대신 승인된 로컬 경로를 선택하세요.")
    resolved = path.resolve()
    if str(resolved).startswith(("\\\\", "//")):
        raise UserError("네트워크 경로 대신 승인된 로컬 경로를 선택하세요.")
    if os.name == "nt":
        import ctypes

        if ctypes.windll.kernel32.GetDriveTypeW(str(resolved.anchor)) == 4:
            raise UserError("네트워크 드라이브는 사용할 수 없습니다.")
    for name in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        root = os.environ.get(name)
        if root and resolved.is_relative_to(Path(root).resolve()):
            raise UserError("동기화 폴더 대신 승인된 로컬 폴더를 선택하세요.")
    known = {"onedrive", "dropbox", "google drive", "googledrive"}
    if any(
        part.casefold() in known or part.casefold().startswith("onedrive - ")
        for part in resolved.parts
    ):
        raise UserError("동기화 폴더 대신 승인된 로컬 폴더를 선택하세요.")
    return resolved


def pages(value: str, total: int, *, duplicates=False) -> list[int]:
    if not value.strip():
        return list(range(total))
    result = []
    for token in value.replace(" ", "").split(","):
        match = re.fullmatch(r"(\d+)(?:[-~](\d+))?", token)
        if not match:
            raise UserError("페이지는 1-3,5,8 또는 3,2,1 형식으로 입력하세요.")
        a = int(match[1])
        b = int(match[2] or a)
        if not 1 <= a <= total or not 1 <= b <= total:
            raise UserError(f"페이지는 1~{total} 범위여야 합니다.")
        seq = range(a - 1, b, 1) if a <= b else range(a - 1, b - 2, -1)
        for n in seq:
            if duplicates or n not in result:
                result.append(n)
    if not result:
        raise UserError("처리할 페이지가 없습니다.")
    return result


def number(value, low, high, label, integer=False):
    try:
        n = int(value) if integer else float(value)
    except (ValueError, TypeError):
        raise UserError(f"{label}에 숫자를 입력하세요.") from None
    if not low <= n <= high:
        raise UserError(f"{label}은 {low}~{high} 범위로 입력하세요.")
    return n


def split_ranges(total, count, boundaries):
    """Boundary pages are one-based starts of the following output file."""
    try:
        if isinstance(count, bool):
            raise ValueError()
        count = int(str(count))
        if isinstance(boundaries, str):
            boundaries = [int(v.strip()) for v in boundaries.split(",")]
        elif isinstance(boundaries, (list, tuple)):
            if any(type(v) is not int for v in boundaries):
                raise ValueError()
        else:
            raise ValueError()
    except (TypeError, ValueError):
        raise UserError("파일 수와 시작 쪽을 정수로 입력하세요. 시작 쪽 예: 5,8") from None
    if not 2 <= count <= total:
        raise UserError(f"파일 수는 2~{total} 사이로 입력하세요.")
    if (
        len(boundaries) != count - 1
        or any(not 2 <= n <= total for n in boundaries)
        or any(a >= b for a, b in zip(boundaries, boundaries[1:]))
    ):
        raise UserError(
            f"다음 파일의 시작 쪽 {count - 1}개를 2~{total} 범위의 오름차순으로 입력하세요."
        )
    starts = [1] + list(boundaries)
    return [
        (start - 1, (starts[i + 1] - 2) if i + 1 < count else total - 1)
        for i, start in enumerate(starts)
    ]


def open_pdf(path, password="", *, extraction=False):
    check_local_path(path)
    try:
        doc = pdf.open(path)
    except Exception:
        raise UserError("파일을 열 수 없습니다. 손상 여부와 읽기 권한을 확인하세요.") from None
    try:
        if not doc.is_pdf:
            raise UserError("PDF 파일을 선택하세요.")
        encrypted = bool((doc.metadata or {}).get("encryption")) or doc.needs_pass
        if encrypted:
            if not password:
                raise UserError("암호화된 PDF입니다. 입력 암호를 입력하세요.")
            auth = doc.authenticate(password)
            if not auth:
                raise UserError("PDF 암호가 올바르지 않습니다.")
            permission = pdf.PDF_PERM_COPY if extraction else pdf.PDF_PERM_MODIFY
            if not auth & 4 and not doc.permissions & permission:
                raise UserError("이 작업의 권한이 없습니다. 소유자 암호를 사용하세요.")
        return doc, encrypted
    except BaseException:
        doc.close()
        raise


def save_pdf(doc, target, password=""):
    opts = dict(garbage=4, deflate=True)
    if password:
        if len(password) > 40:
            raise UserError("PDF 저장 암호는 40자 이하로 입력하세요.")
        opts.update(encryption=pdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    doc.save(target, **opts)
    with pdf.open(target) as verified:
        if password and not verified.authenticate(password):
            raise UserError("저장한 파일의 암호 검증에 실패했습니다.")
        if verified.page_count < 1:
            raise UserError("결과 파일에 페이지가 없습니다.")


def safe_stem(path):
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(path).stem).rstrip(" .")[:70]
    return stem or "document"


def _tick(emit, event, current, total, label="처리 중"):
    check_cancel(event)
    emit({"type": "progress", "current": current, "total": total, "label": label})


def execute(job: dict, emit=lambda message: None, cancel=None) -> Path:
    """Write a new result directory only. A failed/cancelled batch is discarded."""
    paths = [Path(p) for p in job["files"]]
    if not paths:
        raise UserError("파일을 추가하세요.")
    out = check_local_path(job["output"])
    if not out.is_dir():
        raise UserError("저장할 폴더를 선택하세요.")
    if out.is_symlink():
        raise UserError("바로가기 폴더 대신 실제 로컬 폴더를 선택하세요.")
    if os.name == "nt" and str(out).startswith(("\\\\", "//")):
        raise UserError("네트워크 폴더 대신 로컬 폴더를 선택하세요.")
    for path in paths:
        check_local_path(path)
        if not path.is_file():
            raise UserError("선택한 파일을 찾을 수 없습니다.")
    token = job.get("stage_id", uuid.uuid4().hex)
    if not re.fullmatch(r"[a-f0-9]{32}", token):
        raise UserError("작업 식별자가 올바르지 않습니다.")
    stage = out / (".offline-pdf-" + token)
    stage.mkdir(mode=0o700)
    final = out / ("PDF결과_" + datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8])
    try:
        emit({"type": "stage", "folder": str(stage)})
        prepared_paths, converted = prepare_image_inputs(job, paths, stage, emit, cancel)
        _process(job, prepared_paths, stage, emit, cancel)
        check_cancel(cancel)
        os.rename(stage, final)
        if converted and not job.get("options", {}).get("preview_only"):
            emit(
                {
                    "type": "converted",
                    "files": {
                        str(original): str(final / generated.relative_to(stage))
                        for original, generated in converted.items()
                    },
                }
            )
        return final
    finally:
        if stage.exists():
            try:
                shutil.rmtree(stage)
            except OSError:
                raise UserError(
                    "임시자료 정리에 실패했습니다. 저장 폴더의 .offline-pdf- 폴더를 확인해 삭제하세요."
                ) from None


def prepare_image_inputs(job, paths, stage, emit, cancel):
    """Convert images transactionally and keep their positions in mixed inputs.

    Converted inputs are published only after the selected operation succeeds.
    Original images are never overwritten. All frames become PDF pages.
    """
    prepared = []
    converted = {}
    for index, path in enumerate(paths):
        if path.suffix.lower() == ".pdf":
            prepared.append(path)
            continue
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise UserError("PDF 또는 지원하는 이미지 파일을 선택하세요.")
        if path not in converted:
            folder = stage / "입력PDF"
            folder.mkdir(exist_ok=True)
            target = folder / f"{index + 1:03d}_{safe_stem(path)}.pdf"
            _tick(emit, cancel, index, len(paths), "이미지를 PDF로 자동 변환 중")
            with pdf.open() as doc:
                try:
                    for frame in iter_frames(path, lambda: check_cancel(cancel)):
                        if job["tool"] == "images_pdf":
                            landscape = job.get("options", {}).get("orientation") == "가로"
                            width, height = (842, 595) if landscape else (595, 842)
                            page = doc.new_page(width=width, height=height)
                            rect = pdf.Rect(20, 20, width - 20, height - 20)
                        else:
                            page = doc.new_page(width=frame.width, height=frame.height)
                            rect = page.rect
                        page.insert_image(rect, stream=png_bytes(frame), keep_proportion=True)
                    save_pdf(doc, target)
                except ImageReadError as exc:
                    raise UserError(str(exc)) from None
            converted[path] = target
        prepared.append(converted[path])
    return prepared, converted


def _process(job, paths, stage, emit, cancel):
    tool = job["tool"]
    opt = job.get("options", {})
    overlay = None
    if tool in ("watermark", "stamp"):
        if tool == "stamp":
            check_local_path(opt.get("stamp_path", ""))
        try:
            overlay = prepare_overlay(opt, image=tool == "stamp")
        except OverlayError as exc:
            raise UserError(str(exc)) from None
    if tool == "extract" and "page_plan" in opt and len(paths) != 1:
        raise UserError("페이지 정리는 PDF 파일 하나씩 처리하세요.")
    passwords = job.get("passwords", {})

    def password_for(path):
        return passwords.get(str(path), opt.get("input_password", ""))

    output_password = opt.get("output_password", "")
    if tool == "protect" and not output_password:
        raise UserError("설정할 새 암호를 입력하세요.")
    if tool in ("merge", "images_pdf"):
        name = opt.get("output_name", "").strip() or (
            "병합.pdf" if tool == "merge" else "이미지모음.pdf"
        )
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        stem = name[:-4]
        if (
            not stem.strip()
            or len(name) > 120
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
            or stem.endswith((" ", "."))
            or stem.split(".")[0].upper()
            in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *[f"COM{i}" for i in range(1, 10)],
                *[f"LPT{i}" for i in range(1, 10)],
            }
        ):
            raise UserError(
                "저장 파일 이름을 확인하세요. 경로·특수문자·Windows 예약 이름은 사용할 수 없습니다."
            )
        result = pdf.open()
        encrypted_any = False
        inherited_passwords = set()
        try:
            for i, path in enumerate(paths):
                _tick(emit, cancel, i, len(paths), f"{i + 1}/{len(paths)} 파일 처리")
                password = password_for(path)
                src, encrypted = open_pdf(path, password)
                try:
                    result.insert_pdf(src)
                    encrypted_any |= encrypted
                    if encrypted:
                        inherited_passwords.add(password)
                finally:
                    src.close()
            if len(inherited_passwords) > 1 and not output_password:
                raise UserError(
                    "서로 다른 암호의 PDF를 합치려면 결과에 사용할 새 암호를 설정하세요."
                )
            save_pdf(
                result,
                stage / name,
                output_password or (next(iter(inherited_passwords)) if encrypted_any else ""),
            )
        finally:
            result.close()
        return
    for file_index, path in enumerate(paths):
        check_cancel(cancel)
        password = password_for(path)
        extraction = tool in ("pdf_images", "text", "ocr")
        doc, encrypted = open_pdf(path, password, extraction=extraction)
        try:
            prefix = f"{file_index + 1:03d}_{safe_stem(path)}"
            target = stage / (prefix + "_" + tool + ".pdf")
            selected = (
                list(range(doc.page_count))
                if tool == "split" and opt.get("split_mode") == "N개 파일로 나누기"
                else pages(
                    opt.get("pages", ""), doc.page_count, duplicates=(tool in ("extract", "nup"))
                )
            )
            store_password = output_password or (password if encrypted else "")
            if tool == "unlock":
                if encrypted and not doc.authenticate(password) & 4:
                    raise UserError("암호 해제에는 소유자 암호가 필요합니다.")
                save_pdf(doc, target)
            elif tool == "split":
                mode = opt.get("split_mode", "페이지별로 나누기")
                if mode == "N개 파일로 나누기":
                    ranges = split_ranges(
                        doc.page_count, opt.get("split_count", "2"), opt.get("split_starts", "")
                    )
                elif mode == "페이지별로 나누기":
                    ranges = [(n, n) for n in selected]
                else:
                    raise UserError("나누기 방식을 다시 선택하세요.")
                for index, (first, last) in enumerate(ranges):
                    _tick(emit, cancel, index, len(ranges), f"{index + 1}/{len(ranges)} 파일 분할")
                    with pdf.open() as dst:
                        dst.insert_pdf(doc, from_page=first, to_page=last)
                        name = (
                            f"{prefix}_{first + 1:04d}.pdf"
                            if mode == "페이지별로 나누기"
                            else f"{prefix}_{index + 1:04d}_{first + 1}-{last + 1}.pdf"
                        )
                        save_pdf(dst, stage / name, store_password)
            elif tool in ("extract", "delete"):
                if tool == "extract" and "page_plan" in opt:
                    plan = opt["page_plan"]
                    if not isinstance(plan, list) or not plan or len(plan) > 100_000:
                        raise UserError("저장할 페이지 목록을 확인하세요.")
                    for entry in plan:
                        if (
                            not isinstance(entry, dict)
                            or type(entry.get("page")) is not int
                            or not 0 <= entry["page"] < doc.page_count
                            or type(entry.get("rotation")) is not int
                            or entry["rotation"] not in (0, 90, 180, 270)
                        ):
                            raise UserError("페이지 순서나 회전 값이 올바르지 않습니다.")
                    with pdf.open() as dst:
                        for i, entry in enumerate(plan):
                            _tick(emit, cancel, i, len(plan), f"{i + 1}/{len(plan)} 페이지 정리")
                            dst.insert_pdf(doc, from_page=entry["page"], to_page=entry["page"])
                            page = dst[-1]
                            page.set_rotation((page.rotation + entry["rotation"]) % 360)
                        metadata = {
                            key: value
                            for key, value in (doc.metadata or {}).items()
                            if key not in ("format", "encryption")
                        }
                        dst.set_metadata(metadata)
                        save_pdf(dst, target, store_password)
                    continue
                chosen = (
                    selected
                    if tool == "extract"
                    else [n for n in range(doc.page_count) if n not in selected]
                )
                if not chosen:
                    raise UserError("모든 페이지를 삭제할 수 없습니다.")
                doc.select(chosen)
                save_pdf(doc, target, store_password)
            elif tool == "nup":
                from .nup import make_nup

                with make_nup(doc, selected, opt, emit, cancel) as result:
                    check_cancel(cancel)
                    save_pdf(result, target, store_password)
            elif tool == "pdf_images":
                dpi = number(opt.get("dpi", "150"), 72, 300, "해상도", integer=True)
                fmt = str(opt.get("format", "JPG")).lower()
                fmt = {"jpeg": "jpg", "tif": "tiff"}.get(fmt, fmt)
                if fmt.upper() not in EXPORT_FORMATS:
                    raise UserError("JPG·PNG·BMP·GIF·TIFF·WebP 중 저장 형식을 선택하세요.")
                for n in selected:
                    _tick(emit, cancel, n, doc.page_count, f"페이지 {n + 1} 이미지 저장")
                    page = doc[n]
                    if page.rect.width * page.rect.height * (dpi / 72) ** 2 > 60_000_000:
                        raise UserError("페이지가 너무 큽니다. 해상도를 낮추세요.")
                    pix = page.get_pixmap(dpi=dpi, colorspace=pdf.csRGB, alpha=False)
                    save_pixmap(pix, stage / f"{prefix}_{n + 1:04d}.{fmt}", fmt)
            elif tool == "compress":
                level = opt.get("compression", "권장")
                presets = {"선명하게": (300, 90), "권장": (150, 75), "작게": (96, 50)}
                if level != "무손실":
                    if level not in presets:
                        raise UserError("압축 수준을 다시 선택하세요.")
                    dpi, quality = presets[level]
                    _tick(emit, cancel, file_index, len(paths), "이미지 압축 중")
                    doc.rewrite_images(
                        dpi_threshold=int(dpi * 1.2), dpi_target=dpi, quality=quality, bitonal=False
                    )
                    check_cancel(cancel)
                save_pdf(doc, target, store_password)
            elif tool == "upscale":
                from .enhance import comparison, enhance_pdf

                if opt.get("preview_only"):
                    if len(paths) != 1:
                        raise UserError("미리보기는 PDF 하나씩 선택하세요.")
                    comparison(doc, stage, opt, emit, cancel)
                else:
                    enhance_pdf(doc, opt, emit, cancel)
                    save_pdf(doc, target, store_password)
            elif tool == "text":
                with (stage / f"{prefix}.txt").open("w", encoding="utf-8-sig") as output:
                    for n in selected:
                        _tick(emit, cancel, n, doc.page_count, f"페이지 {n + 1} 문자 추출")
                        output.write(f"\n--- {n + 1}쪽 ---\n" + doc[n].get_text(sort=True))
            elif tool == "ocr":
                tessdata = Path(opt.get("tessdata", ""))
                language = opt.get("language", "kor+eng")
                if not str(opt.get("tessdata", "")).strip():
                    raise UserError("오프라인 OCR 언어자료 폴더를 선택하세요.")
                try:
                    with model_directory(tessdata, language) as model_path, pdf.open() as dst:
                        for n in selected:
                            _tick(emit, cancel, n, doc.page_count, f"페이지 {n + 1} OCR")
                            page = doc[n]
                            if page.rect.width * page.rect.height * (200 / 72) ** 2 > 40_000_000:
                                raise UserError("OCR 페이지가 너무 큽니다.")
                            try:
                                pix = page.get_pixmap(dpi=200, colorspace=pdf.csRGB, alpha=False)
                                data = pix.pdfocr_tobytes(language=language, tessdata=model_path)
                            except Exception as exc:
                                detail = str(exc).lower()
                                if any(
                                    word in detail
                                    for word in ("tesseract", "tessdata", "ocr initial", "no ocr")
                                ):
                                    raise UserError(
                                        "OCR 엔진 또는 언어자료를 불러오지 못했습니다. 배포본을 다시 압축 해제하거나 언어자료 폴더를 확인하세요."
                                    ) from None
                                raise UserError(
                                    f"{n + 1}쪽의 OCR 처리에 실패했습니다. 해당 페이지를 확인하거나 다른 문서로 다시 시도하세요."
                                ) from None
                            with pdf.open("pdf", data) as one:
                                dst.insert_pdf(one)
                        save_pdf(dst, target, store_password)
                except OCRSetupError as exc:
                    raise UserError(str(exc)) from None
            else:
                for index, n in enumerate(selected):
                    _tick(
                        emit,
                        cancel,
                        index,
                        len(selected),
                        f"{file_index + 1}/{len(paths)} 파일 · {n + 1}쪽",
                    )
                    page = doc[n]
                    if tool == "rotate":
                        angle = number(opt.get("angle", "90"), 90, 270, "회전 각도", integer=True)
                        if angle not in (90, 180, 270):
                            raise UserError("90·180·270도 중 선택하세요.")
                        page.set_rotation((page.rotation + angle) % 360)
                    elif tool in ("watermark", "stamp"):
                        try:
                            overlay.draw(page)
                        except OverlayError as exc:
                            raise UserError(str(exc)) from None
                    elif tool == "number":
                        start = number(opt.get("start", "1"), 0, 999999, "시작 번호", integer=True)
                        rect = (
                            pdf.Rect(
                                10,
                                page.rect.height - 35,
                                page.rect.width - 10,
                                page.rect.height - 10,
                            )
                            * page.derotation_matrix
                        )
                        page.insert_textbox(rect, str(start + index), fontsize=11, align=1)
                    elif tool == "crop":
                        margin = number(opt.get("margin", "10"), 0, 100, "여백 자르기") * 72 / 25.4
                        rect = page.cropbox + (margin, margin, -margin, -margin)
                        if rect.is_empty:
                            raise UserError("자를 여백이 페이지보다 큽니다.")
                        page.set_cropbox(rect)
                    elif tool == "redact":
                        regions = opt.get("regions", {}).get(str(n), [])
                        for coords in regions:
                            r = pdf.Rect(coords) * page.derotation_matrix
                            page.add_redact_annot(r, fill=(0, 0, 0))
                        if regions:
                            page.apply_redactions(images=2, graphics=2, text=0)
                    elif tool not in ("compress", "protect", "clean"):
                        raise UserError("지원하지 않는 기능입니다.")
                if tool == "redact":
                    count = sum(len(v) for v in opt.get("regions", {}).values())
                    if not count:
                        raise UserError("미리보기에서 삭제할 영역을 그리세요.")
                    # Erase off-page data too: cropped PDFs are deliberately refused by UI/engine.
                    for page in doc:
                        if page.cropbox != page.mediabox:
                            raise UserError(
                                "잘린 페이지가 있는 PDF는 영구 삭제를 지원하지 않습니다. 원본 PDF를 사용하세요."
                            )
                    doc.scrub(
                        attached_files=True,
                        embedded_files=True,
                        javascript=True,
                        metadata=True,
                        xml_metadata=True,
                        redactions=False,
                        hidden_text=False,
                        clean_pages=True,
                        remove_links=True,
                        reset_fields=True,
                        reset_responses=True,
                        thumbnails=True,
                    )
                    for page in doc:
                        for widget in list(page.widgets() or []):
                            page.delete_widget(widget)
                        for annot in list(page.annots() or []):
                            page.delete_annot(annot)
                if tool == "clean":
                    doc.scrub(
                        attached_files=True,
                        embedded_files=True,
                        javascript=True,
                        metadata=True,
                        xml_metadata=True,
                        redactions=False,
                        hidden_text=False,
                        clean_pages=True,
                        remove_links=False,
                        reset_fields=False,
                        reset_responses=True,
                        thumbnails=True,
                    )
                save_pdf(doc, target, store_password)
        finally:
            doc.close()


def worker(job, queue, cancel):
    disable_network()
    try:
        result = execute(job, queue.put, cancel)
        queue.put({"type": "done", "folder": str(result)})
    except Cancelled:
        queue.put({"type": "cancelled"})
    except UserError as exc:
        queue.put({"type": "error", "message": str(exc)})
    except Exception as exc:
        # Never expose document data, passwords, paths or raw library exceptions.
        queue.put(
            {
                "type": "error",
                "message": f"처리하지 못했습니다 ({type(exc).__name__}). 파일 형식·저장 권한·디스크 여유 공간을 확인하세요.",
            }
        )
