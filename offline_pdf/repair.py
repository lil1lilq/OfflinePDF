"""Conservative, local PDF structure recovery using the existing MuPDF engine."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

import pymupdf as pdf

from .engine import Cancelled, UserError, check_cancel, check_local_path, disable_network

REPAIR_FAILED = (
    "PDF 구조를 자동으로 복구할 수 없습니다.\n"
    "크롬에서 파일을 열어 인쇄 → PDF로 저장한 뒤 다시 추가하세요. 원본은 보관하세요."
)
ENCRYPTION_FAILED = (
    "PDF 암호화 정보가 올바르지 않아 구조를 복구할 수 없습니다.\n"
    "크롬에서 파일을 열어 인쇄 → PDF로 저장한 뒤 다시 추가하세요. 원본은 보관하세요."
)


def open_failure_message(error):
    """MuPDF's useful format error is usually wrapped by FileDataError."""
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if "encryption" in str(error).lower():
            return ENCRYPTION_FAILED
        error = error.__cause__ or error.__context__
    return REPAIR_FAILED


def needs_repair(path):
    """Password-protected, otherwise healthy PDFs follow the normal password flow."""
    path = check_local_path(path)
    try:
        with pdf.open(path) as doc:
            return doc.is_pdf and doc.is_repaired
    except pdf.FileDataError as exc:
        if open_failure_message(exc) == ENCRYPTION_FAILED:
            raise UserError(ENCRYPTION_FAILED) from None
        return True


def _page_signature(page):
    """Check content without flattening the saved document into images."""
    rect = page.rect
    if rect.is_empty or rect.is_infinite:
        raise UserError(REPAIR_FAILED)
    scale = min(1, 256 / max(rect.width, rect.height))
    pixmap = page.get_pixmap(matrix=pdf.Matrix(scale, scale), annots=True)
    return (
        tuple(page.mediabox),
        tuple(page.cropbox),
        page.rotation,
        hashlib.sha256(page.get_text().encode("utf-8")).digest(),
        hashlib.sha256(pixmap.samples).digest(),
    )


def publish_repaired(staged, destination):
    """Never replace an original or an existing result, including a race at save time."""
    destination = check_local_path(destination)
    if destination.suffix.lower() != ".pdf":
        raise UserError("복구본은 .pdf 파일로 저장하세요.")
    created = False
    try:
        with destination.open("xb") as output:
            created = True
            with Path(staged).open("rb") as source:
                shutil.copyfileobj(source, output)
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError:
        raise UserError("이미 있는 파일은 덮어쓰지 않습니다. 다른 파일명을 선택하세요.") from None
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return destination


def repair_pdf(source, destination, *, cancel=None, progress=None):
    """Rebuild xrefs/objects; reject encryption/signatures rather than guessing keys.

    The caller owns staging storage. The input is never saved or modified. A full
    reopen and per-page text/geometry/render comparison precedes publication.
    """
    source, destination = check_local_path(source), check_local_path(destination)
    if source == destination or destination.exists():
        raise UserError("이미 있는 파일은 덮어쓰지 않습니다. 다른 파일명을 선택하세요.")
    if destination.suffix.lower() != ".pdf":
        raise UserError("복구본은 .pdf 파일로 저장하세요.")
    check_cancel(cancel)
    try:
        doc = pdf.open(source)
    except pdf.FileDataError as exc:
        raise UserError(open_failure_message(exc)) from None
    with doc:
        if not doc.is_pdf or not doc.page_count:
            raise UserError(REPAIR_FAILED)
        if doc.needs_pass or (doc.metadata or {}).get("encryption"):
            raise UserError(
                "암호화된 PDF는 구조 복구를 지원하지 않습니다. 원본은 변경하지 않았습니다."
            )
        if doc.get_sigflags() > 0:
            raise UserError(
                "전자서명 양식이 있는 PDF는 구조 복구를 지원하지 않습니다. 원본은 변경하지 않았습니다."
            )
        signatures = []
        for index, page in enumerate(doc):
            check_cancel(cancel)
            signatures.append(_page_signature(page))
            if progress:
                progress(index + 1, doc.page_count * 2)
        # All temporary files live in caller-owned storage so process cancellation
        # can remove them even when native parsing does not return promptly.
        with tempfile.TemporaryDirectory(
            prefix=".offlinepdf-repair-", dir=destination.parent
        ) as folder:
            staged = Path(folder) / "rebuilt.pdf"
            doc.save(staged, garbage=3, deflate=True)
            check_cancel(cancel)
            with pdf.open(staged) as rebuilt:
                if (
                    rebuilt.is_repaired
                    or rebuilt.needs_pass
                    or rebuilt.page_count != len(signatures)
                ):
                    raise UserError(REPAIR_FAILED)
                for index, page in enumerate(rebuilt):
                    check_cancel(cancel)
                    if _page_signature(page) != signatures[index]:
                        raise UserError(
                            "복구 전후의 페이지 내용이 달라 복구본을 저장하지 않았습니다."
                        )
                    if progress:
                        progress(len(signatures) + index + 1, len(signatures) * 2)
            check_cancel(cancel)
            return publish_repaired(staged, destination)


def repair_worker(source, destination, events, cancel):
    disable_network()
    try:
        repair_pdf(source, destination, cancel=cancel)
        events.put(("done", ""))
    except Cancelled:
        events.put(("cancelled", ""))
    except UserError as exc:
        events.put(("error", str(exc)))
    except OSError:
        events.put(
            ("error", "복구본을 저장할 수 없습니다. 저장 위치와 읽기·쓰기 권한을 확인하세요.")
        )
    except Exception:
        events.put(("error", REPAIR_FAILED))
