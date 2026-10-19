"""Text and image placement shared by the combined insertion tool."""

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


@dataclass
class Overlay:
    position: str
    opacity: float
    text: str = ""
    font_size: float = 24
    image: bytes = b""
    width: float = 100
    aspect: float = 1

    def draw(self, page):
        available_width = page.rect.width - 40
        available_height = page.rect.height - 40
        if available_width <= 0 or available_height <= 0:
            raise OverlayError("페이지가 너무 작아 삽입할 수 없습니다.")
        if self.image:
            width, height = self.width, self.width / self.aspect
        else:
            # A fixed line box accommodates Korean and Latin glyphs while the
            # user controls font size. Reject overflow instead of clipping text.
            width = available_width
            height = max(50, self.font_size * 2.5)
        if width > available_width or height > available_height:
            raise OverlayError("삽입할 내용이 페이지보다 큽니다. 크기를 줄이세요.")
        horizontal, vertical = POSITIONS[self.position]
        x = 20 + (available_width - width) * horizontal
        y = 20 + (available_height - height) * vertical
        rect = pdf.Rect(x, y, x + width, y + height) * page.derotation_matrix
        if self.image:
            page.insert_image(rect, stream=self.image, keep_proportion=True, rotate=page.rotation)
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
    overlay.width = numeric(options.get("stamp_width", "100"), 10, 400, "이미지 너비")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as source:
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise OverlayError("이미지가 너무 큽니다. 크기를 줄여 주세요.")
                # Use the first frame for a stamp; preserve its existing alpha.
                with ImageOps.exif_transpose(source) as oriented, oriented.convert("RGBA") as rgba:
                    overlay.aspect = rgba.width / rgba.height
                    with rgba.getchannel("A") as alpha:
                        rgba.putalpha(alpha.point([round(i * opacity) for i in range(256)]))
                    with BytesIO() as output:
                        rgba.save(output, format="PNG")
                        overlay.image = output.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise OverlayError(
            "이미지를 읽지 못했습니다. 파일 형식과 손상 여부를 확인하세요."
        ) from None
    return overlay
