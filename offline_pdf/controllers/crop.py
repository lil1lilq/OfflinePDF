"""Eight crop handles; update lightweight overlays during a drag."""

from ..crop import MM, SIDES, resized_crop
from ..ui import BLUE


class CropController:
    def crop_options_changed(self, *_):
        if getattr(self, "_crop_syncing", False):
            return
        self._crop_drag = None
        self.arrange_fields()
        self.update_file_summary()
        self.schedule_preview()

    def crop_reset(self):
        if self.busy():
            return
        self._crop_syncing = True
        try:
            for side in SIDES:
                self.options[f"margin_{side}"].set("0")
        finally:
            self._crop_syncing = False
        self._crop_drag = None
        self.refresh_preview()

    def draw_crop_overlay(self):
        for tag in ("crop_shade", "crop_boundary", "crop_handle"):
            self.canvas.delete(tag)
        self._crop_handles = {}
        rect = getattr(self, "_crop_box", None)
        if not rect or not self.preview_rect:
            return
        scale = self.preview_scale
        left, top, right, bottom = (12 + n * scale for n in rect)
        width, height = self.preview_rect
        for edge in (
            (12, 12, 12 + width * scale, top),
            (12, bottom, 12 + width * scale, 12 + height * scale),
            (12, top, left, bottom),
            (right, top, 12 + width * scale, bottom),
        ):
            if edge[2] > edge[0] and edge[3] > edge[1]:
                self.canvas.create_rectangle(
                    *edge, fill="#374151", outline="", stipple="gray50", tags="crop_shade"
                )
        self.canvas.create_rectangle(
            left, top, right, bottom, outline=BLUE, dash=(4, 3), tags="crop_boundary"
        )
        middle_x, middle_y = (left + right) / 2, (top + bottom) / 2
        self._crop_handles = {
            "nw": (left, top),
            "n": (middle_x, top),
            "ne": (right, top),
            "w": (left, middle_y),
            "e": (right, middle_y),
            "sw": (left, bottom),
            "s": (middle_x, bottom),
            "se": (right, bottom),
        }
        for x, y in self._crop_handles.values():
            self.canvas.create_rectangle(
                x - 4, y - 4, x + 4, y + 4, fill="white", outline=BLUE, tags="crop_handle"
            )

    def crop_handle_at(self, event):
        if self.tool != "crop" or self.active_thumbnail_view():
            return None
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        return next(
            (
                name
                for name, (hx, hy) in getattr(self, "_crop_handles", {}).items()
                if abs(hx - x) <= 9 and abs(hy - y) <= 9
            ),
            None,
        )

    def preview_hover(self, event):
        if self.tool == "crop":
            self.canvas.config(cursor="hand2" if self.crop_handle_at(event) else "")
        else:
            self.stamp_hover(event)

    def crop_drag_start(self, event):
        handle = self.crop_handle_at(event)
        if not handle:
            return
        if self.preview_timer:
            self.root.after_cancel(self.preview_timer)
            self.preview_timer = None
        self._crop_drag = (handle, self.canvas_point(event), tuple(self._crop_box))

    def crop_drag_move(self, event):
        drag = getattr(self, "_crop_drag", None)
        if not drag or self.busy():
            return
        handle, start, rect = drag
        point = self.canvas_point(event)
        values = resized_crop(
            rect, handle, point[0] - start[0], point[1] - start[1], self.preview_rect
        )
        self._crop_syncing = True
        try:
            moved = {"left": "w", "top": "n", "right": "e", "bottom": "s"}
            for side in SIDES:
                if moved[side] in handle:
                    self.options[f"margin_{side}"].set(
                        f"{values[side]:.2f}".rstrip("0").rstrip(".")
                    )
        finally:
            self._crop_syncing = False
        width, height = self.preview_rect
        self._crop_box = (
            values["left"] * MM,
            values["top"] * MM,
            width - values["right"] * MM,
            height - values["bottom"] * MM,
        )
        self.draw_crop_overlay()

    def crop_drag_end(self, event):
        if getattr(self, "_crop_drag", None):
            self.crop_drag_move(event)
            self._crop_drag = None
            self.refresh_preview()
