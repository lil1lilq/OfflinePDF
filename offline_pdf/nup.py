"""Vector-preserving A4 imposition shared by export and preview."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pymupdf as pdf

from .engine import UserError, check_cancel, number


@dataclass(frozen=True)
class NupLayout:
    count: int
    columns: int
    rows: int
    width: float
    height: float
    margin: float
    gap: float
    fill: bool
    vertical: bool

    @classmethod
    def from_options(cls, options, source_rect):
        count = number(options.get("nup_count", "4"), 1, 64, "한 장당 쪽수", integer=True)
        columns = number(options.get("nup_columns", "0"), 0, count, "가로 칸 수", integer=True)
        orientation = options.get("nup_orientation", "세로")
        fit = options.get("nup_fit", "전체 내용 유지")
        order = options.get("nup_order", "가로 우선")
        if orientation not in ("세로", "가로"):
            raise UserError("A4 방향을 다시 선택하세요.")
        if fit not in ("전체 내용 유지", "꽉 채우기 (잘림)"):
            raise UserError("채우기 방식을 다시 선택하세요.")
        if order not in ("가로 우선", "세로 우선"):
            raise UserError("배치 순서를 다시 선택하세요.")
        width, height = pdf.paper_size("a4")
        if orientation == "가로":
            width, height = height, width
        mm = 72 / 25.4
        margin = number(options.get("nup_margin", "0"), 0, 100, "바깥 여백(mm)") * mm
        gap = number(options.get("nup_gap", "0"), 0, 100, "쪽 사이 간격(mm)") * mm

        def cell_size(cols):
            rows = math.ceil(count / cols)
            return (
                (width - 2 * margin - (cols - 1) * gap) / cols,
                (height - 2 * margin - (rows - 1) * gap) / rows,
            )

        if not columns:
            # Maximize the first selected page's visible area; use fewer empty cells on ties.
            def score(cols):
                cw, ch = cell_size(cols)
                area = (
                    min(cw / source_rect.width, ch / source_rect.height) ** 2
                    if cw > 0 and ch > 0
                    else -1
                )
                return area, -(cols * math.ceil(count / cols) - count)

            columns = max(range(1, count + 1), key=score)
        cw, ch = cell_size(columns)
        if cw <= 0 or ch <= 0:
            raise UserError("배치할 공간이 없습니다. 여백·간격이나 가로 칸 수를 줄이세요.")
        return cls(
            count,
            columns,
            math.ceil(count / columns),
            width,
            height,
            margin,
            gap,
            fit == "꽉 채우기 (잘림)",
            order == "세로 우선",
        )

    def cell(self, index):
        row, col = (
            (index % self.rows, index // self.rows)
            if self.vertical
            else divmod(index, self.columns)
        )
        cw = (self.width - 2 * self.margin - (self.columns - 1) * self.gap) / self.columns
        ch = (self.height - 2 * self.margin - (self.rows - 1) * self.gap) / self.rows
        x = self.margin + col * (cw + self.gap)
        y = self.margin + row * (ch + self.gap)
        return pdf.Rect(x, y, x + cw, y + ch)


def make_nup(source, selected, options, emit=lambda message: None, cancel=None, sheet=None):
    """Return a new document; sheet selects one output sheet for a bounded preview.

    Copy/bake annotations and form appearances, then handle rotations explicitly on an
    in-memory copy. Links and interactive fields are not carried to the output.
    Cropping is visual clipping, not redaction.
    """
    if not selected:
        raise UserError("모아찍기할 페이지가 없습니다.")
    layout = NupLayout.from_options(options, source[selected[0]].rect)
    total = math.ceil(len(selected) / layout.count)
    sheets = range(total) if sheet is None else [max(0, min(sheet, total - 1))]
    needed = list(
        dict.fromkeys(
            n for s in sheets for n in selected[s * layout.count : (s + 1) * layout.count]
        )
    )
    result = pdf.open()
    try:
        with pdf.open() as normalized:
            mapping = {}
            for i, n in enumerate(needed):
                check_cancel(cancel)
                normalized.insert_pdf(
                    source,
                    from_page=n,
                    to_page=n,
                    links=False,
                    annots=True,
                    widgets=True,
                    final=int(i == len(needed) - 1),
                )
                mapping[n] = i
            normalized.bake(annots=True, widgets=True)
            rotations = {}
            for page in normalized:
                check_cancel(cancel)
                rotations[page.number] = page.rotation
                page.set_rotation(0)
            for s in sheets:
                check_cancel(cancel)
                target = result.new_page(width=layout.width, height=layout.height)
                batch = selected[s * layout.count : (s + 1) * layout.count]
                for slot, n in enumerate(batch):
                    check_cancel(cancel)
                    index = mapping[n]
                    page = normalized[index]
                    cell = layout.cell(slot)
                    clip = pdf.Rect(page.rect)
                    if layout.fill:
                        ratio = (
                            cell.height / cell.width
                            if rotations[index] % 180
                            else cell.width / cell.height
                        )
                        if clip.width / clip.height > ratio:
                            trim = (clip.width - clip.height * ratio) / 2
                            clip.x0 += trim
                            clip.x1 -= trim
                        else:
                            trim = (clip.height - clip.width / ratio) / 2
                            clip.y0 += trim
                            clip.y1 -= trim
                    if page.get_contents():
                        target.show_pdf_page(
                            cell, normalized, index, clip=clip, rotate=-rotations[index]
                        )
                    emit(
                        {
                            "type": "progress",
                            "current": s * layout.count + slot + 1,
                            "total": len(selected),
                            "label": f"A4 모아찍기 {s + 1}/{total}장",
                        }
                    )
        return result
    except BaseException:
        result.close()
        raise
