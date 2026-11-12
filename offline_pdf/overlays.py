"""Text and image placement shared by the combined insertion tool."""

import json
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pymupdf as pdf
from PIL import Image, ImageOps

from .images import IMAGE_EXTENSIONS, MAX_IMAGE_PIXELS

POSITIONS = {
    "왼쪽 위": (0, 0),
    "가운데 위": (0.5, 0),
    "오른쪽 위": (1, 0),
    "가운데": (0.5, 0.5),
    "왼쪽 아래": (0, 1),
    "가운데 아래": (0.5, 1),
    "오른쪽 아래": (1, 1),
}


class OverlayError(Exception):
    pass


def numeric(value, minimum, maximum, label):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise OverlayError(f"{label} 값을 확인하세요.") from None
    if not minimum <= result <= maximum:
        raise OverlayError(f"{label}: {minimum}~{maximum} 범위로 입력하세요.")
    return result


def remove_light_background(image, tolerance=30):
    """Remove near-white paper, preserving existing alpha and dark/colored ink.

    Process bounded row strips and unmatte faded edges against white to avoid
    a white halo on top of document text. No network or source-file writes.
    """
    import numpy as np

    result = image.copy()
    rows = max(1, 250_000 // image.width)
    cutoff = 255 - tolerance
    for top in range(0, image.height, rows):
        bottom = min(image.height, top + rows)
        with image.crop((0, top, image.width, bottom)) as strip:
            pixels = np.array(strip, dtype=np.float32)
        coverage = np.clip((cutoff - pixels[:, :, :3].min(axis=2)) / 20, 0, 1)
        pixels[:, :, :3] = np.clip(
            (pixels[:, :, :3] - 255 * (1 - coverage[:, :, None]))
            / np.maximum(coverage[:, :, None], 1 / 255),
            0,
            255,
        )
        pixels[:, :, 3] *= coverage
        with Image.fromarray(np.rint(pixels).astype(np.uint8)) as processed:
            result.paste(processed, (0, top))
    return result


def relative_rect(value):
    if not value:
        return None
    try:
        coords = json.loads(value) if isinstance(value, str) else value
        if not isinstance(coords, (list, tuple)) or len(coords) != 4:
            raise ValueError()
        x, y, right, bottom = (float(v) for v in coords)
        if not (0 <= x < right <= 1 and 0 <= y < bottom <= 1):
            raise ValueError()
        return (x, y, right, bottom)
    except (TypeError, ValueError, OverflowError):
        raise OverlayError("이미지 위치와 크기를 다시 지정하세요.") from None


@dataclass
class Overlay:
    position: str
    opacity: float
    text: str = ""
    font_size: float = 24
    image: bytes = b""
    width: float = 100
    aspect: float = 1
    height: float | None = None
    relative: tuple | None = None
    lock_aspect: bool = False

    def image_rect(self, page):
        if self.relative:
            x, y, right, bottom = self.relative
            if self.lock_aspect:
                width = (right - x) * page.rect.width
                height = width / self.aspect
                if height > page.rect.height:
                    width *= page.rect.height / height
                    height = page.rect.height
                left = min(x * page.rect.width, page.rect.width - width)
                top = min(y * page.rect.height, page.rect.height - height)
                return pdf.Rect(left, top, left + width, top + height)
            return pdf.Rect(
                x * page.rect.width,
                y * page.rect.height,
                right * page.rect.width,
                bottom * page.rect.height,
            )
        return self.placement(page)

    def placement(self, page):
        available_width = page.rect.width - 40
        available_height = page.rect.height - 40
        if available_width <= 0 or available_height <= 0:
            raise OverlayError("페이지가 너무 작아 삽입할 수 없습니다.")
        if self.image:
            width, height = self.width, self.height or self.width / self.aspect
        else:
            width = available_width
            height = max(50, self.font_size * 2.5)
        if width > available_width or height > available_height:
            raise OverlayError("삽입할 내용이 페이지보다 큽니다. 크기를 줄이세요.")
        horizontal, vertical = POSITIONS[self.position]
        x = 20 + (available_width - width) * horizontal
        y = 20 + (available_height - height) * vertical
        return pdf.Rect(x, y, x + width, y + height)

    def draw(self, page):
        visible = self.image_rect(page) if self.image else self.placement(page)
        rect = visible * page.derotation_matrix
        horizontal, _ = POSITIONS[self.position]
        if self.image:
            page.insert_image(rect, stream=self.image, keep_proportion=False, rotate=page.rotation)
        elif (
            page.insert_textbox(
                rect,
                self.text,
                fontname="korea",
                fontsize=self.font_size,
                align=round(horizontal * 2),
                rotate=page.rotation,
                color=(0.35, 0.35, 0.35),
                fill_opacity=self.opacity,
            )
            < 0
        ):
            raise OverlayError("문구가 영역보다 큽니다. 글자 크기를 줄이세요.")


def prepare_overlay(options, *, image=False):
    position = options.get("position", "오른쪽 아래" if image else "가운데")
    if position not in POSITIONS:
        raise OverlayError("삽입 위치를 다시 선택하세요.")
    opacity = numeric(options.get("opacity", "1" if image else "0.25"), 0.05, 1, "불투명도")
    overlay = Overlay(position, opacity)
    if not image:
        overlay.text = options.get("text", "").strip()
        if not overlay.text:
            raise OverlayError("삽입할 문구를 입력하세요.")
        overlay.font_size = numeric(options.get("font_size", "24"), 8, 72, "글자 크기")
        return overlay
    path = Path(options.get("stamp_path", ""))
    if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise OverlayError("지원하는 이미지 파일을 선택하세요.")
    overlay.width = numeric(options.get("stamp_width", "100"), 1, 20000, "이미지 너비")
    if str(options.get("stamp_height", "")).strip():
        overlay.height = numeric(options["stamp_height"], 1, 20000, "이미지 높이")
    overlay.relative = relative_rect(options.get("stamp_rect"))
    overlay.lock_aspect = options.get("stamp_lock") == "유지"
    remove = options.get("remove_background", "사용 안 함") == "사용"
    tolerance = numeric(options.get("background_tolerance", "30"), 0, 120, "배경 제거 강도")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as source:
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise OverlayError("이미지가 너무 큽니다. 크기를 줄여 주세요.")
                # Use the first frame for a stamp; preserve its existing alpha.
                with ImageOps.exif_transpose(source) as oriented:
                    rgba = oriented.convert("RGBA")
                try:
                    if remove:
                        cleaned = remove_light_background(rgba, tolerance)
                        rgba.close()
                        rgba = cleaned
                    overlay.aspect = rgba.width / rgba.height
                    with rgba.getchannel("A") as alpha:
                        rgba.putalpha(alpha.point([round(i * opacity) for i in range(256)]))
                    with BytesIO() as output:
                        rgba.save(output, format="PNG")
                        overlay.image = output.getvalue()
                finally:
                    rgba.close()
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise OverlayError(
            "이미지를 읽지 못했습니다. 파일 형식과 손상 여부를 확인하세요."
        ) from None
    return overlay
