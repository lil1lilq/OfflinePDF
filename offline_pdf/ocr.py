"""Prepare a local ASCII model path for Tesseract on Windows."""

import ctypes
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path


class OCRSetupError(Exception):
    pass


def short_path(path):
    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        fn = kernel.GetShortPathNameW
        fn.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        fn.restype = ctypes.c_uint
        size = fn(str(path), None, 0)
        if not size:
            return None
        buffer = ctypes.create_unicode_buffer(size)
        if not fn(str(path), buffer, size):
            return None
        return buffer.value if buffer.value.isascii() else None
    except (AttributeError, OSError):
        return None


def cache_roots():
    yield tempfile.gettempdir()
    for key in ("TEMP", "LOCALAPPDATA", "PROGRAMDATA", "PUBLIC"):
        if os.environ.get(key):
            yield os.environ[key]


@contextmanager
def model_directory(source, language, *, windows=None):
    from .engine import check_local_path

    source = check_local_path(source)
    languages = language.split("+")
    if not languages or any(lang not in {"kor", "eng"} for lang in languages):
        raise OCRSetupError("OCR 언어는 한국어·영어 중 선택하세요.")
    if not source.is_dir():
        raise OCRSetupError("OCR 언어자료 폴더를 찾을 수 없습니다. 폴더를 다시 선택하세요.")
    for lang in languages:
        path = source / (lang + ".traineddata")
        check_local_path(path)
        if not path.is_file() or path.stat().st_size == 0:
            raise OCRSetupError(f"OCR 언어자료 {lang}.traineddata가 없거나 비어 있습니다.")
    if windows is None:
        windows = os.name == "nt"
    if not windows or str(source).isascii():
        yield str(source)
        return
    alias = short_path(source)
    if alias:
        yield alias
        return
    # Copy public language models only, never user documents or recognized text.
    temporary = None
    for candidate in cache_roots():
        try:
            base = check_local_path(candidate)
            if not str(base).isascii():
                alias = short_path(base)
                if not alias:
                    continue
                base = Path(alias)
            if not base.is_dir():
                continue
            temporary = tempfile.TemporaryDirectory(prefix="offlinepdf-ocr-", dir=str(base))
            break
        except (OSError, ValueError):
            continue
        except Exception:
            # A blocked network/cloud candidate must not prevent trying local roots.
            continue
    if temporary is None:
        raise OCRSetupError(
            "OCR 언어자료용 영문 경로를 준비하지 못했습니다. 프로그램을 C:\\OfflinePDF 같은 영문 경로로 옮긴 뒤 다시 시도하세요."
        )
    with temporary as destination:
        try:
            for lang in languages:
                shutil.copyfile(
                    source / (lang + ".traineddata"), Path(destination) / (lang + ".traineddata")
                )
        except OSError:
            raise OCRSetupError(
                "OCR 언어자료를 준비하지 못했습니다. 임시 폴더 권한과 여유 공간을 확인하세요."
            ) from None
        yield destination
