"""Virtualized overview shared by tools that do not edit page order."""

import math

import pymupdf as pdf

from .engine import crop_page_rect, pages
from .organizer import PageOrder, PageOrganizer


class ThumbnailOverview(PageOrganizer):
    editable = False

    def load(self, path, password=""):
        super().load(path, password)
        if self.doc and self.app.tool == "nup":
            from .nup import NupLayout

            options = {key: value.get() for key, value in self.app.options.items()}
            selected = pages(options.get("pages", ""), self.doc.page_count, duplicates=True)
            layout = NupLayout.from_options(options, self.doc[selected[0]].rect)
            count = math.ceil(len(selected) / layout.count)
            if len(self.model.items) != count:
                self.model = PageOrder(count)
                self.cache.clear()

    def thumbnail_page(self, n):
        options = {key: value.get() for key, value in self.app.options.items()}
        tool = self.app.tool
        if tool == "nup":
            from .nup import make_nup

            chosen = pages(options.get("pages", ""), self.doc.page_count, duplicates=True)
            temporary = make_nup(self.doc, chosen, options, sheet=n)
            return temporary[0], temporary
        temporary = pdf.open()
        try:
            temporary.insert_pdf(self.doc, from_page=n, to_page=n)
            page = temporary[0]
            chosen = pages(options.get("pages", ""), self.doc.page_count)
            if n in chosen:
                if tool == "number":
                    from .numbering import draw_number

                    draw_number(page, chosen.index(n), options)
                elif tool == "watermark":
                    from .overlays import prepare_overlay

                    if not self.app.stamp_mode() or options.get("stamp_path"):
                        prepare_overlay(options, image=bool(self.app.stamp_mode())).draw(page)
                elif tool == "crop":
                    margin = crop_page_rect(page, options).x0 - page.cropbox.x0
                    bounds = page.rect
                    rect = bounds + (margin, margin, -margin, -margin)
                    for edge in (
                        (0, 0, bounds.width, rect.y0),
                        (0, rect.y1, bounds.width, bounds.height),
                        (0, rect.y0, rect.x0, rect.y1),
                        (rect.x1, rect.y0, bounds.width, rect.y1),
                    ):
                        page.draw_rect(edge, color=None, fill=(0.22, 0.25, 0.32), fill_opacity=0.4)
            if tool == "redact":
                for rect in self.app.regions.get(self.app.selected_file(), {}).get(str(n), []):
                    page.draw_rect(
                        rect, color=(0.8, 0.1, 0.1), fill=(0.8, 0.1, 0.1), fill_opacity=0.4
                    )
            return page, temporary
        except Exception:
            temporary.close()
            raise

    def update_summary(self):
        if self.model:
            self.app.page_label.config(text=f"전체 {len(self.model.items)}쪽")

    def press(self, event):
        if self.model and not self.app.busy():
            i = self.hit(event.x, event.y)
            if i is not None:
                self.model.selected = {self.model.items[i][0]}
                self.app.page_index = i
                self.draw()

    def motion(self, event):
        return

    def release(self, event):
        return

    def double_click(self, event):
        if self.hit(event.x, event.y) is not None and not self.app.busy():
            self.press(event)
            self.app.show_preview()
        return "break"

    def enlarge(self):
        self.app.show_preview()

    def delete(self):
        return

    def rotate(self):
        return

    def undo(self):
        return

    def keyboard_move(self, delta):
        return "break"
