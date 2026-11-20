"""Display-space crop geometry shared by preview interaction and PDF output."""

import math

import pymupdf as pdf

MM = 72 / 25.4
MIN_CROP = MM
SIDES = ("left", "top", "right", "bottom")


def crop_values(options):
    from .engine import number

    return {
        side: number(
            options.get(f"margin_{side}", options.get("margin", "10")), 0, 100000, "여백 mm"
        )
        for side in SIDES
    }


def visible_crop_rect(page, options):
    from .engine import UserError

    values = crop_values(options)
    bounds = page.rect
    rect = pdf.Rect(
        values["left"] * MM,
        values["top"] * MM,
        bounds.width - values["right"] * MM,
        bounds.height - values["bottom"] * MM,
    )
    if rect.is_empty:
        raise UserError("자를 여백이 페이지보다 큽니다.")
    if rect.width < MIN_CROP - 1e-6 or rect.height < MIN_CROP - 1e-6:
        raise UserError("남길 영역은 가로·세로 1mm 이상이어야 합니다.")
    return rect


def cropbox_rect(page, options):
    visible = visible_crop_rect(page, options)
    rect = visible * page.derotation_matrix
    offset = page.cropbox
    return pdf.Rect(
        rect.x0 + offset.x0, rect.y0 + offset.y0, rect.x1 + offset.x0, rect.y1 + offset.y0
    )


def crop_pages(options, total):
    from .engine import UserError, pages

    scope = options.get("crop_scope")
    if scope == "현재 페이지":
        return pages(str(options.get("crop_page", "1")), total)
    if scope == "전체 페이지":
        return list(range(total))
    if scope not in (None, "지정 페이지"):
        raise UserError("여백 적용 범위를 확인하세요.")
    if scope == "지정 페이지" and not str(options.get("pages", "")).strip():
        raise UserError("적용할 페이지 번호를 입력하세요.")
    return pages(options.get("pages", ""), total)


def resized_crop(rect, handle, dx, dy, bounds):
    """Clamp eight handles in visible page coordinates, then round outwards."""
    left, top, right, bottom = rect
    width, height = bounds
    if "w" in handle:
        left = max(0, min(right - MIN_CROP, left + dx))
    if "e" in handle:
        right = min(width, max(left + MIN_CROP, right + dx))
    if "n" in handle:
        top = max(0, min(bottom - MIN_CROP, top + dy))
    if "s" in handle:
        bottom = min(height, max(top + MIN_CROP, bottom + dy))
    values = (left / MM, top / MM, (width - right) / MM, (height - bottom) / MM)
    moved = {"left": "w", "top": "n", "right": "e", "bottom": "s"}
    return {
        side: math.floor(max(0, value) * 100 + 1e-8) / 100 if moved[side] in handle else value
        for side, value in zip(SIDES, values)
    }
