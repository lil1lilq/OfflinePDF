"""Interactive image overlay on the existing PDF preview canvas."""

from __future__ import annotations

import json
import math
import tkinter as tk
from io import BytesIO

from PIL import Image, ImageTk

from .. import ctk_widgets as ttk
from ..engine import check_local_path, pages
from ..overlays import OverlayError, prepare_overlay
from ..ui import BLUE


def resize_rect(rect, corner, point, bounds, aspect=None):
    """Resize against the opposite corner without crossing it or page edges."""
    x0, y0, x1, y1 = rect
    sx = -1 if corner in ("nw", "sw") else 1
    sy = -1 if corner in ("nw", "ne") else 1
    ax, ay = (x1 if sx < 0 else x0), (y1 if sy < 0 else y0)
    maxw = ax if sx < 0 else bounds[0] - ax
    maxh = ay if sy < 0 else bounds[1] - ay
    width = min(maxw, max(1, sx * (point[0] - ax)))
    height = min(maxh, max(1, sy * (point[1] - ay)))
    if aspect:
        width = min(max(width, height * aspect), maxw, maxh * aspect)
        height = width / aspect
    px, py = ax + sx * width, ay + sy * height
    return (min(ax, px), min(ay, py), max(ax, px), max(ay, py))


def handle_points(rect):
    x0, y0, x1, y1 = rect
    return (
        ("nw", x0, y0),
        ("ne", x1, y0),
        ("se", x1, y1),
        ("sw", x0, y1),
        ("n", (x0 + x1) / 2, y0),
        ("e", x1, (y0 + y1) / 2),
        ("s", (x0 + x1) / 2, y1),
        ("w", x0, (y0 + y1) / 2),
    )


def stretch_rect(rect, edge, point, bounds):
    x0, y0, x1, y1 = rect
    if edge == "n":
        y0 = max(0, min(y1 - 1, point[1]))
    elif edge == "s":
        y1 = min(bounds[1], max(y0 + 1, point[1]))
    elif edge == "w":
        x0 = max(0, min(x1 - 1, point[0]))
    elif edge == "e":
        x1 = min(bounds[0], max(x0 + 1, point[0]))
    return x0, y0, x1, y1


class StampController:
    def stamp_mode(self):
        return (
            self.tool == "watermark"
            and self.options.get("insert_mode")
            and self.options["insert_mode"].get() == "이미지"
        )

    def setup_stamp_controls(self):
        self.stamp_original = False
        self._stamp_drag = None
        self._stamp_syncing = False
        self._stamp_cache_key = None
        self._stamp_page_size = None
        if getattr(self, "_stamp_source", None):
            self._stamp_source.close()
        self._stamp_source = None
        self.field("이미지 높이 pt (공란=자동)", "stamp_height", "")
        self.field("배경 제거", "remove_background", "사용", ["사용", "사용 안 함"])
        self.field("배경 제거 강도 (0~120)", "background_tolerance", "30")
        self.options["stamp_rect"] = tk.StringVar()
        cell = ttk.Frame(self.form, style="Panel.TFrame")
        self.form_cells.append(("stamp_actions", cell))
        self.stamp_original_button = ttk.Button(
            cell, text="원본 보기", command=self.toggle_stamp_original
        )
        self.stamp_original_button.pack(side="left", padx=3)
        ttk.Button(cell, text="위치·크기 초기화", command=self.reset_stamp).pack(
            side="left", padx=3
        )
        for key in (
            "stamp_path",
            "stamp_width",
            "stamp_height",
            "position",
            "opacity",
            "remove_background",
            "background_tolerance",
            "pages",
        ):
            self.options[key].trace_add("write", lambda *_, key=key: self.stamp_changed(key))

    def stamp_changed(self, key):
        if self._stamp_syncing or not self.stamp_mode():
            return
        self._stamp_syncing = True
        try:
            if key == "stamp_path":
                self.options["stamp_rect"].set("")
                self.options["stamp_height"].set("")
                self.stamp_original = False
                self.stamp_original_button.config(text="원본 보기")
            elif key == "position":
                self.options["stamp_rect"].set("")
            elif key in ("stamp_width", "stamp_height"):
                try:
                    width = float(self.options["stamp_width"].get())
                    height = float(
                        self.options["stamp_height"].get()
                        or width / getattr(self, "_stamp_aspect", 1)
                    )
                    if math.isfinite(width) and math.isfinite(height) and width > 0 and height > 0:
                        value = self.options["stamp_rect"].get()
                        if value and self._stamp_page_size:
                            x, y, _, _ = json.loads(value)
                            pw, ph = self._stamp_page_size
                            if width > pw or height > ph:
                                raise ValueError()
                            x, y = min(x, 1 - width / pw), min(y, 1 - height / ph)
                            self.options["stamp_rect"].set(
                                json.dumps((x, y, x + width / pw, y + height / ph))
                            )
                    else:
                        raise ValueError()
                except (ValueError, TypeError, ZeroDivisionError):
                    # Discard the custom box so invalid controls cannot save an old size.
                    self.options["stamp_rect"].set("")
        finally:
            self._stamp_syncing = False
        self.arrange_fields()
        if key == "stamp_path" and self.options["stamp_path"].get():
            self.show_preview()
        else:
            self.schedule_preview()

    def reset_stamp(self):
        if self.busy() or not self.stamp_mode():
            return
        self._stamp_syncing = True
        self.options["stamp_rect"].set("")
        self.options["stamp_width"].set("100")
        self.options["stamp_height"].set("")
        self.options["position"].set("오른쪽 아래")
        self._stamp_syncing = False
        self.stamp_original = False
        self.stamp_original_button.config(text="원본 보기")
        self.schedule_preview()

    def toggle_stamp_original(self):
        if self.busy() or not self.stamp_mode():
            return
        self.stamp_original = not self.stamp_original
        self.stamp_original_button.config(
            text="배경 제거 결과 보기" if self.stamp_original else "원본 보기"
        )
        self.schedule_preview()

    def preview_stamp(self, page, total):
        self.canvas.delete("stamp")
        self._stamp_drag = None
        self._stamp_box = None
        options = {key: value.get() for key, value in self.options.items()}
        if not options.get("stamp_path"):
            self.status.set(
                "이미지를 선택한 뒤 미리보기에서 드래그해 배치하세요. 페이지 공란은 전체에 적용됩니다."
            )
            return
        if self.page_index not in pages(options.get("pages", ""), total):
            self.status.set("이 페이지는 적용 범위에 포함되지 않습니다.")
            return
        path = check_local_path(options["stamp_path"])
        stat = path.stat()
        # Geometry and page changes reuse the decoded image; original viewing is
        # display-only and never mutates the options passed to the save worker.
        key = (
            str(path),
            stat.st_size,
            stat.st_mtime_ns,
            options["opacity"],
            options["remove_background"],
            options["background_tolerance"],
            self.stamp_original,
        )
        if self.stamp_original:
            options["remove_background"] = "사용 안 함"
        try:
            if key != self._stamp_cache_key:
                overlay = prepare_overlay(options, image=True)
                with Image.open(BytesIO(overlay.image)) as image:
                    source = image.convert("RGBA")
                if self._stamp_source:
                    self._stamp_source.close()
                self._stamp_source = source
                self._stamp_cache_key = key
                self._stamp_aspect = overlay.aspect
            else:
                # Layout calculation must still validate current numeric fields.
                from ..overlays import Overlay, numeric, relative_rect

                overlay = Overlay(
                    options["position"],
                    1,
                    image=b"cached",
                    width=numeric(options["stamp_width"], 1, 20000, "이미지 너비"),
                    aspect=self._stamp_aspect,
                    height=numeric(options["stamp_height"], 1, 20000, "이미지 높이")
                    if options["stamp_height"]
                    else None,
                    relative=relative_rect(options["stamp_rect"]),
                )
            rect = overlay.image_rect(page)
            self._stamp_page_size = (page.rect.width, page.rect.height)
            self._stamp_box = tuple(rect)
            if overlay.relative:
                self._stamp_syncing = True
                try:
                    self.options["stamp_width"].set(f"{rect.width:.3f}")
                    self.options["stamp_height"].set(f"{rect.height:.3f}")
                finally:
                    self._stamp_syncing = False
            self.draw_stamp_layer()
            self.status.set(
                "원본 보기 중입니다. 저장에는 배경 제거 설정이 적용됩니다."
                if self.stamp_original
                else "안쪽: 이동 · 모서리: 비율 유지 크기 조절 · 변 중앙: 한 방향 늘리기 · 페이지 공란: 전체 적용 · 인증서 전자서명이 아닙니다."
            )
        except OverlayError as exc:
            self.status.set(str(exc))
            raise

    def draw_stamp_layer(self):
        self.canvas.delete("stamp")
        if not self._stamp_box or not self._stamp_source:
            return
        box = [12 + value * self.preview_scale for value in self._stamp_box]
        width, height = max(1, round(box[2] - box[0])), max(1, round(box[3] - box[1]))
        with self._stamp_source.resize((width, height), Image.Resampling.LANCZOS) as image:
            self._stamp_photo = ImageTk.PhotoImage(image, master=self.canvas)
        self.canvas.create_image(box[0], box[1], anchor="nw", image=self._stamp_photo, tags="stamp")
        self.canvas.create_rectangle(*box, outline=BLUE, width=2, tags="stamp")
        for _, x, y in handle_points(box):
            self.canvas.create_rectangle(
                x - 5, y - 5, x + 5, y + 5, fill="white", outline=BLUE, width=2, tags="stamp"
            )

    def stamp_handle_at(self, event):
        if not self.stamp_mode() or self.busy() or not getattr(self, "_stamp_box", None):
            return None
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        for name, px, py in handle_points(self._stamp_box):
            if (
                abs(x - (12 + px * self.preview_scale)) <= 7
                and abs(y - (12 + py * self.preview_scale)) <= 7
            ):
                return name
        return None

    def stamp_hover(self, event):
        self.canvas.config(cursor="hand2" if self.stamp_handle_at(event) else "")

    def stamp_drag_start(self, event):
        if self.busy() or not getattr(self, "_stamp_box", None):
            return
        point = self.canvas_point(event)
        rect = self._stamp_box
        handle = self.stamp_handle_at(event)
        if handle:
            self._stamp_drag = (handle, point, rect)
            return
        if rect[0] <= point[0] <= rect[2] and rect[1] <= point[1] <= rect[3]:
            self._stamp_drag = ("move", point, rect)

    def stamp_drag_move(self, event):
        if self.busy() or not getattr(self, "_stamp_drag", None):
            return
        kind, start, rect = self._stamp_drag
        point = self.canvas_point(event)
        pw, ph = self._stamp_page_size
        if kind == "move":
            dx = min(pw - rect[2], max(-rect[0], point[0] - start[0]))
            dy = min(ph - rect[3], max(-rect[1], point[1] - start[1]))
            self._stamp_box = (rect[0] + dx, rect[1] + dy, rect[2] + dx, rect[3] + dy)
        elif kind in ("n", "e", "s", "w"):
            self._stamp_box = stretch_rect(rect, kind, point, (pw, ph))
        else:
            aspect = (rect[2] - rect[0]) / (rect[3] - rect[1])
            self._stamp_box = resize_rect(rect, kind, point, (pw, ph), aspect)
        self.draw_stamp_layer()

    def stamp_drag_end(self, event):
        if self.busy() or not getattr(self, "_stamp_drag", None):
            return
        self.stamp_drag_move(event)
        self._stamp_drag = None
        x0, y0, x1, y1 = self._stamp_box
        pw, ph = self._stamp_page_size
        self._stamp_syncing = True
        self.options["stamp_rect"].set(json.dumps((x0 / pw, y0 / ph, x1 / pw, y1 / ph)))
        self.options["stamp_width"].set(f"{x1 - x0:.3f}")
        self.options["stamp_height"].set(f"{y1 - y0:.3f}")
        self._stamp_syncing = False
