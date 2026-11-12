"""Page-number placement shared by preview and final output."""

import pymupdf as pdf

from .engine import UserError, number
from .overlays import POSITIONS


def draw_number(page, index, options):
    start = number(options.get("start", "1"), 0, 999999, "시작 번호", integer=True)
    size = number(options.get("number_font_size", "11"), 8, 72, "쪽 번호 글자 크기")
    position = options.get("number_position", "가운데 아래")
    if position not in POSITIONS:
        raise UserError("쪽 번호 위치를 다시 선택하세요.")
    text = str(start + index)
    width = pdf.get_text_length(text, fontname="helv", fontsize=size) + 4
    height = size * 1.8 + 4
    if width > page.rect.width - 20 or height > page.rect.height - 20:
        raise UserError("쪽 번호가 페이지보다 큽니다. 글자 크기를 줄이세요.")
    horizontal, vertical = POSITIONS[position]
    x = 10 + (page.rect.width - 20 - width) * horizontal
    y = 10 + (page.rect.height - 20 - height) * vertical
    rect = pdf.Rect(x, y, x + width, y + height) * page.derotation_matrix
    if (
        page.insert_textbox(
            rect,
            text,
            fontsize=size,
            fontname="helv",
            align=round(horizontal * 2),
            rotate=page.rotation,
        )
        < 0
    ):
        raise UserError("쪽 번호를 삽입할 수 없습니다. 글자 크기를 줄이세요.")
