"""Scrollable, cached page thumbnails with reversible split boundaries."""

import math

from .organizer import PageOrganizer
from .ui import BG, BLUE, FONT, LINE, RED


def separator_line(boundary, columns, cellw, cellh):
    row, column = divmod(boundary, columns)
    if column:
        x = column * cellw
        return x, row * cellh + 8, x, (row + 1) * cellh - 16
    y = row * cellh - 6
    return 8, y, columns * cellw - 8, y


class SplitPreview(PageOrganizer):
    split_view = True

    def __init__(self, master, app):
        self.separators = {}
        self.cut_hover = None
        self.cut_press = None
        super().__init__(master, app)
        self.order_label.pack_forget()

    def load(self, path, password=""):
        changed = self.path is not None and (not path or not self.matches(path))
        if changed:
            self.set_cuts(set())
        super().load(path, password)

    def cuts(self):
        count = len(self.model.items) if self.model else 0
        if self.app.options["split_mode"].get() == "페이지별로 나누기":
            return set(range(1, count))
        try:
            return {
                int(v.strip()) - 1
                for v in self.app.options["split_starts"].get().split(",")
                if v.strip()
            }
        except ValueError:
            return set()

    def set_cuts(self, cuts):
        self.app.split_updating = True
        try:
            self.app.options["split_starts"].set(",".join(str(n + 1) for n in sorted(cuts)))
            self.app.options["split_count"].set(str(max(2, len(cuts) + 1)))
        finally:
            self.app.split_updating = False
        self.app.update_split_preview()

    def update_summary(self):
        if self.app.tool != "split":
            return
        count = len(self.model.items) if self.model else 0
        self.app.page_index = max(0, min(self.app.page_index, count - 1))
        self.app.page_label.config(
            text=f"{self.app.page_index + 1} / {count}쪽" if count else "미리보기"
        )
        self.app.zoom_label.config(text=f"{round(self.tile_width.get() / 220 * 100)}%")

    def draw(self):
        super().draw()
        self.separators = {}
        if not self.model or self.app.tool != "split":
            return
        count = len(self.model.items)
        first = max(1, int(self.canvas.canvasy(0) / self.cellh) * self.columns)
        last = min(
            count,
            (int(self.canvas.canvasy(self.canvas.winfo_height()) / self.cellh) + 2) * self.columns,
        )
        cuts = self.cuts()
        for boundary in range(first, last):
            line = separator_line(boundary, self.columns, self.cellw, self.cellh)
            self.separators[boundary] = line
            active = boundary in cuts
            color = RED if active else BLUE if self.cut_hover == boundary else LINE
            self.canvas.create_line(*line, fill=color, width=2, dash=(5, 4), tags="cut_line")
            x, y = (line[0] + line[2]) / 2, (line[1] + line[3]) / 2
            self.canvas.create_oval(
                x - 12, y - 12, x + 12, y + 12, fill=BG, outline=color, tags="cut_handle"
            )
            if active:
                for rect in ((x - 8, y - 8, x - 2, y - 2), (x - 8, y + 2, x - 2, y + 8)):
                    self.canvas.create_oval(*rect, outline=color, width=2, tags="cut_scissors")
                self.canvas.create_line(
                    x - 3, y - 4, x + 7, y + 6, fill=color, width=2, tags="cut_scissors"
                )
                self.canvas.create_line(
                    x - 3, y + 4, x + 7, y - 6, fill=color, width=2, tags="cut_scissors"
                )
            else:
                self.canvas.create_text(x, y, text="+", fill=color, font=(FONT, 13), tags="cut_add")

    def hit_cut(self, x, y):
        y = self.canvas.canvasy(y)
        nearest, distance = None, 13
        for boundary, (x0, y0, x1, y1) in self.separators.items():
            dx = max(min(x0, x1) - x, 0, x - max(x0, x1))
            dy = max(min(y0, y1) - y, 0, y - max(y0, y1))
            gap = math.hypot(dx, dy)
            if gap < distance:
                nearest, distance = boundary, gap
        return nearest

    def clear_hover(self):
        self.cut_hover = None
        self.canvas.configure(cursor="")
        self.draw()

    def press(self, event):
        if self.app.start_zoom_drag(event, self):
            return
        if self.app.busy() or not self.model:
            return
        self.cut_press = (self.hit_cut(event.x, event.y), event.x, event.y)
        i = self.hit(event.x, event.y)
        if self.cut_press[0] is None and i is not None:
            self.app.page_index = i
            self.model.selected = {self.model.items[i][0]}
            self.draw()

    def motion(self, event):
        self.app.move_zoom_drag(event)

    def release(self, event):
        if self.app.end_zoom_drag(event):
            return
        pressed, self.cut_press = self.cut_press, None
        if not pressed or self.app.busy():
            return
        boundary, x, y = pressed
        if boundary is None or abs(event.x - x) + abs(event.y - y) > 6:
            return
        if self.hit_cut(event.x, event.y) != boundary:
            return
        cuts = self.cuts()
        cuts.symmetric_difference_update({boundary})
        self.app.split_updating = True
        self.app.options["split_mode"].set("N개 파일로 나누기")
        self.app.split_updating = False
        self.set_cuts(cuts)
        self.draw()

    def mouse_hover(self, event):
        boundary = self.hit_cut(event.x, event.y)
        self.canvas.configure(cursor="hand2" if boundary is not None else "")
        if boundary != self.cut_hover:
            self.cut_hover = boundary
            self.draw()

    def double_click(self, event):
        pass

    def select_all(self, force=None):
        pass

    def delete(self):
        pass

    def undo(self):
        pass

    def keyboard_move(self, delta):
        return "break"
