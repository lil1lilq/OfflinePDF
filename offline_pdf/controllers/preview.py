"""Width-fit document preview, organizer and actual AI comparison."""

from __future__ import annotations

import base64
import math
import shutil
import tkinter as tk
from pathlib import Path

import pymupdf as pdf

from .. import ctk_widgets as ttk
from .. import theme
from ..engine import UserError, check_local_path, crop_page_rect, open_pdf, pages
from ..images import open_image_document
from ..overlays import OverlayError
from ..passwords import cached_password
from ..ui import BLUE, PANEL


class PreviewController:
    """Width-fit document preview, organizer and actual AI comparison."""

    def show_preview_toolbar(self):
        if not self.preview_zoom_row.winfo_manager():
            visible = self.document_host.pack_slaves()
            options = {"before": visible[0]} if visible else {}
            self.preview_zoom_row.pack(fill="x", pady=(0, 8), **options)

    def ensure_preview_visible(self):
        if not self.selected_file() or self.screen == "comparison":
            return False
        if self.work.winfo_manager() and not self.preview_panel.winfo_manager():
            self.show_preview()
            self.root.update_idletasks()
        return True

    def show_preview(self):
        if self.tool == "split":
            self.show_document_view(restore=False)
            return
        self.split_view.pack_forget()
        self.show_preview_toolbar()
        # General tools open directly on the document with settings visible.
        focused = self.tool == "extract"
        if focused and self.screen != "preview":
            self.preview_origin = self.capture_preview_origin()
        self.organizer.pack_forget()
        if focused or self.settings_panel_needed():
            self.columns.pack(fill="x", before=self.document_host)
        else:
            self.columns.pack_forget()
        self.preview_panel.pack(fill="both", expand=True, pady=(8, 0))
        self.schedule_preview()
        if self.work.winfo_manager():
            self.screen = "preview" if focused else "work"
        self.update_back_state()

    def show_document_view(self, restore=True):
        self.show_preview_toolbar()
        self.split_view.pack_forget()
        if self.tool == "split":
            self.preview_panel.pack_forget()
            self.organizer.pack_forget()
            self.columns.pack(fill="x", before=self.document_host)
            self.split_view.pack(fill="both", expand=True)
            self.screen = "work"
            self.schedule_preview()
            self.update_back_state()
            return
        # General tools have a single document view; only the organizer has a
        # separate thumbnail editing view to return to.
        if self.tool != "extract":
            self.preview_origin = None
            self.show_preview()
            return
        origin = self.preview_origin if restore else None
        self.preview_origin = None
        if origin:
            self.file_list.selection_clear(0, "end")
            for i, path in enumerate(self.files):
                if path in origin["selected_paths"]:
                    self.file_list.selection_set(i)
            if self.files and not self.file_list.curselection():
                self.file_list.selection_set(0)
            self.page_index = origin["page"]
            self.organizer_preview_uid = origin["organizer_uid"]
            self.file_list.yview_moveto(origin["file_y"])
            if self.tool == "extract" and origin["organizer_path"]:
                self.organizer.load(
                    self.selected_file(), cached_password(self, self.selected_file())
                )
                if (
                    self.organizer.path == origin["organizer_path"]
                    and self.organizer.fingerprint == origin["organizer_fingerprint"]
                ):
                    self.organizer.model = origin["organizer_model"]
        self.preview_panel.pack_forget()
        self.organizer.pack_forget()
        self.columns.pack(fill="x", before=self.document_host)
        self.organizer.pack(fill="both", expand=True)
        if self.work.winfo_manager():
            self.screen = "work"
        if origin:
            self.root.after_idle(lambda: self.organizer.scroll_to("moveto", origin["organizer_y"]))
            self.schedule_preview()
        self.update_back_state()

    def set_preview_mode(self, mode):
        if not self.ensure_preview_visible():
            return
        grid = self.active_thumbnail_view()
        if grid:
            grid.tile_width.set(max(160, grid.canvas.winfo_width()) if mode == "width" else 220)
            grid.draw()
            return
        self.preview_mode = mode
        self.preview_zoom = 1.0
        self.canvas.xview_moveto(0)
        self.refresh_preview()

    def zoom_preview(self, delta):
        if not self.ensure_preview_visible():
            return
        grid = self.active_thumbnail_view()
        if grid:
            grid.tile_width.set(max(160, min(640, grid.tile_width.get() + round(delta * 220))))
            grid.draw()
            return
        self.preview_zoom = max(0.25, min(3.0, self.preview_zoom + delta))
        self.refresh_preview()

    def active_thumbnail_view(self):
        view = (
            self.split_view
            if self.tool == "split"
            else self.organizer
            if self.tool == "extract"
            else None
        )
        return view if view and view.winfo_manager() else None

    def start_zoom_drag(self, event, grid=None):
        if not getattr(event, "state", 0) & 4:
            self._zoom_drag = None
            return False
        if self.busy() or not self.selected_file():
            return True
        value = grid.tile_width.get() if grid else self.preview_zoom
        self._zoom_drag = (event.y, value, grid, getattr(event, "x", 0))
        self._zoom_moved = False
        (grid.canvas if grid else self.canvas).configure(cursor="sb_v_double_arrow")
        return True

    def move_zoom_drag(self, event):
        drag = getattr(self, "_zoom_drag", None)
        if drag is None:
            return False
        y, initial, grid, x = drag
        if abs(event.y - y) + abs(getattr(event, "x", x) - x) <= 6 and not self._zoom_moved:
            return True
        self._zoom_moved = True
        factor = math.exp(max(-4, min(4, (y - event.y) / 160)))
        if grid:
            grid.tile_width.set(round(max(160, min(640, initial * factor))))
        else:
            self.preview_zoom = max(0.25, min(3.0, initial * factor))
        if not getattr(self, "_zoom_timer", None):
            self._zoom_timer = self.root.after(33, self.render_drag_zoom)
        return True

    def render_drag_zoom(self):
        self._zoom_timer = None
        drag = getattr(self, "_zoom_drag", None)
        if drag is None:
            return
        grid = drag[2]
        if grid:
            grid.draw()
        else:
            self.refresh_preview()

    def end_zoom_drag(self, event):
        if getattr(self, "_zoom_drag", None) is None:
            return False
        self.move_zoom_drag(event)
        if getattr(self, "_zoom_timer", None):
            self.root.after_cancel(self._zoom_timer)
            self._zoom_timer = None
        self.render_drag_zoom()
        grid = self._zoom_drag[2]
        (grid.canvas if grid else self.canvas).configure(cursor="")
        self._zoom_drag = None
        return True

    def refresh_organizer(self):
        if self.tool != "extract":
            return
        path = self.selected_file()
        self.organizer.load(path, cached_password(self, path))
        if not self.preview_panel.winfo_manager():
            self.show_document_view()
        self.update_file_summary()
        self.organizer.update_summary()

    def show_ai_comparison(self, folder):
        # Keep one back control. The comparison is another navigation level.
        self.comparison_origin = self.screen
        self.comparison_folder = folder
        self.comparison_frame = ttk.Frame(self.document_host, padding=10)
        for widget in self.document_host.winfo_children():
            widget.pack_forget()
        self.columns.pack_forget()
        self.comparison_frame.pack(fill="both", expand=True)
        ttk.Label(
            self.comparison_frame,
            text="선택 문서의 첫 스캔 이미지 중앙 영역 · 실제 AI 보정 결과",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(self.comparison_frame)
        row.pack(fill="both", expand=True)
        row.columnconfigure((0, 1), weight=1, uniform="comparison")
        row.rowconfigure(0, weight=1)
        from PIL import Image, ImageTk

        self.comparison_photos = {}
        self.comparison_images = []
        for i, (caption, name) in enumerate(
            [("원본 확대", "before.png"), ("AI 보정 후", "after.png")]
        ):
            cell = ttk.Frame(row)
            cell.grid(row=0, column=i, sticky="nsew", padx=5)
            ttk.Label(cell, text=caption, font=(theme.BOLD_FAMILY, 14, "bold")).pack(
                anchor="w", pady=5
            )
            with Image.open(Path(folder) / name) as image:
                source = image.copy()
                self.comparison_images.append(source)
            canvas = tk.Canvas(cell, width=100, height=120, bg=PANEL, highlightthickness=0)
            canvas.pack(fill="both", expand=True)

            def draw(event, canvas=canvas, source=source):
                picture = source.copy()
                picture.thumbnail((max(1, event.width - 10), max(1, event.height - 10)))
                photo = ImageTk.PhotoImage(picture)
                picture.close()
                self.comparison_photos[canvas] = photo
                canvas.delete("all")
                canvas.create_image(event.width / 2, 5, anchor="n", image=photo)

            canvas.bind("<Configure>", draw)
        self.screen = "comparison"
        self.update_back_state()

    def close_ai_comparison(self):
        if not self.comparison_folder:
            return
        self.comparison_frame.destroy()
        self.comparison_photos = {}
        for image in self.comparison_images:
            image.close()
        self.comparison_images = []
        shutil.rmtree(self.comparison_folder, ignore_errors=True)
        self.comparison_folder = None
        self.screen = self.comparison_origin
        self.show_preview_toolbar()
        if self.screen == "preview":
            self.preview_panel.pack(fill="both", expand=True, pady=(8, 0))
            self.schedule_preview()
        else:
            self.show_document_view(restore=False)
        self.update_back_state()

    def schedule_preview(self):
        if self.preview_timer:
            self.root.after_cancel(self.preview_timer)
        self.preview_timer = self.root.after(250, self.refresh_preview)

    def refresh_preview(self, reset=False):
        self.preview_timer = None
        self.canvas.delete("all")
        self.preview_rect = None
        self._stamp_box = None
        self._stamp_drag = None
        self.canvas.config(cursor="")
        if reset:
            self.page_index = 0
            self.canvas.yview_moveto(0)
        path = self.selected_file()
        if self.tool == "split":
            self.split_view.load(path, cached_password(self, path))
            self.split_view.draw()
            return
        if not path:
            self.canvas.config(scrollregion=(0, 0, max(300, self.canvas.winfo_width()), 280))
            text = "파일을 추가하면 여기에서 미리 볼 수 있습니다."
            if self.file_drop and self.file_drop.enabled:
                text = "파일을 여기에 끌어놓거나\n파일 추가 버튼으로 선택하세요."
            self.canvas.create_text(15, 25, anchor="nw", text=text)
            self.page_label.config(text="미리보기")
            return
        try:
            check_local_path(path)
            password = cached_password(self, path)
            if Path(path).suffix.lower() == ".pdf":
                doc, _ = open_pdf(path, password, extraction=True)
            else:
                doc = open_image_document(path)
            nup_doc = None
            try:
                preview_total = doc.page_count
                preview_index = None
                if self.tool == "nup":
                    from ..nup import NupLayout, make_nup

                    options = {key: value.get() for key, value in self.options.items()}
                    selected = pages(options.get("pages", ""), doc.page_count, duplicates=True)
                    layout = NupLayout.from_options(options, doc[selected[0]].rect)
                    preview_total = math.ceil(len(selected) / layout.count)
                    self.page_index = max(0, min(self.page_index, preview_total - 1))
                    preview_index = self.page_index
                    nup_doc = make_nup(doc, selected, options, sheet=preview_index)
                angle = 0
                if self.tool == "extract" and self.organizer.model:
                    item = next(
                        (
                            p
                            for p in self.organizer.model.items
                            if p[0] == self.organizer_preview_uid
                        ),
                        self.organizer.model.items[0],
                    )
                    self.organizer_preview_uid = item[0]
                    self.page_index = item[1]
                    angle = item[2]
                if nup_doc is None:
                    self.page_index = max(0, min(self.page_index, doc.page_count - 1))
                page = nup_doc[0] if nup_doc is not None else doc[self.page_index]
                if self.tool == "number":
                    from ..numbering import draw_number

                    options = {key: value.get() for key, value in self.options.items()}
                    chosen = pages(options.get("pages", ""), doc.page_count)
                    if self.page_index in chosen:
                        draw_number(page, chosen.index(self.page_index), options)
                crop_margin = None
                if self.tool == "crop":
                    options = {key: value.get() for key, value in self.options.items()}
                    chosen = pages(options.get("pages", ""), doc.page_count)
                    if self.page_index in chosen:
                        crop_margin = crop_page_rect(page, options).x0 - page.cropbox.x0
                rw, rh = (
                    (page.rect.height, page.rect.width)
                    if angle % 180
                    else (page.rect.width, page.rect.height)
                )
                w = max(self.canvas.winfo_width() - 24, 150)
                h = max(100, self.canvas.winfo_height() - 24)
                fit = min(w / rw, h / rh) if self.preview_mode == "page" else w / rw
                self.preview_scale = min(
                    fit * self.preview_zoom, math.sqrt(16_000_000 / (rw * rh)), 20_000 / rh
                )
                pix = page.get_pixmap(
                    matrix=pdf.Matrix(self.preview_scale, self.preview_scale).prerotate(angle),
                    alpha=False,
                    colorspace=pdf.csRGB,
                )
                self.preview_photo = tk.PhotoImage(data=base64.b64encode(pix.tobytes("png")))
                self.canvas.create_image(12, 12, anchor="nw", image=self.preview_photo)
                self.preview_rect = (page.rect.width, page.rect.height)
                self.canvas.configure(scrollregion=(0, 0, pix.width + 24, pix.height + 24))
                if crop_margin is not None and crop_margin > 0:
                    margin = crop_margin * self.preview_scale
                    x, y, right, bottom = 12, 12, 12 + pix.width, 12 + pix.height
                    for rect in (
                        (x, y, right, y + margin),
                        (x, bottom - margin, right, bottom),
                        (x, y + margin, x + margin, bottom - margin),
                        (right - margin, y + margin, right, bottom - margin),
                    ):
                        self.canvas.create_rectangle(
                            *rect, fill="#374151", outline="", stipple="gray50", tags="crop_shade"
                        )
                    self.canvas.create_rectangle(
                        x + margin,
                        y + margin,
                        right - margin,
                        bottom - margin,
                        outline=BLUE,
                        dash=(4, 3),
                        tags="crop_boundary",
                    )
                self.zoom_label.config(text=f"{round(self.preview_zoom * 100)}%")
                self.page_label.config(text=f"{self.page_index + 1} / {preview_total}쪽")
                if self.tool == "extract" and self.organizer.model:
                    position = next(
                        (
                            i
                            for i, p in enumerate(self.organizer.model.items)
                            if p[0] == self.organizer_preview_uid
                        ),
                        0,
                    )
                    self.page_label.config(
                        text=f"원본 {self.page_index + 1}쪽 · 정리 후 {position + 1}/{len(self.organizer.model.items)}"
                    )
                if self.stamp_mode():
                    self.preview_stamp(page, doc.page_count)
                if self.tool == "redact":
                    for coords in self.regions.get(path, {}).get(str(self.page_index), []):
                        self.canvas.create_rectangle(
                            *[12 + c * self.preview_scale for c in coords],
                            outline="#d32f2f",
                            width=2,
                            stipple="gray50",
                            fill="#d32f2f",
                        )
            finally:
                if nup_doc is not None:
                    nup_doc.close()
                doc.close()
        except (UserError, OverlayError) as exc:
            self.canvas.create_text(15, 25, anchor="nw", width=420, text=str(exc))
            self.page_label.config(text="설정을 확인하세요")
        except Exception:
            self.canvas.create_text(
                15,
                25,
                anchor="nw",
                width=320,
                text="미리보기를 열 수 없습니다.\n잠긴 파일은 왼쪽 목록에서 클릭해 암호를 입력하세요.",
            )
        self.update_region_status()

    def preview_wheel(self, event):
        step = (
            (-1 if event.num == 4 else 1) if event.num in (4, 5) else (-1 if event.delta > 0 else 1)
        )
        self.canvas.yview_scroll(step * 3, "units")
        return "break"

    def turn(self, delta):
        if not self.ensure_preview_visible():
            return
        if self.tool == "extract" and self.organizer.model:
            items = self.organizer.model.items
            i = next((j for j, p in enumerate(items) if p[0] == self.organizer_preview_uid), 0)
            self.organizer_preview_uid = items[max(0, min(len(items) - 1, i + delta))][0]
            self.refresh_preview()
            return
        self.page_index = max(0, self.page_index + delta)
        if self.tool == "split" and self.split_view.model:
            view = self.split_view
            self.page_index = min(self.page_index, len(view.model.items) - 1)
            view.model.selected = {view.model.items[self.page_index][0]}
            row = self.page_index // view.columns
            view.canvas.yview_moveto(
                row * view.cellh / max(1, float(view.canvas.cget("scrollregion").split()[-1]))
            )
            view.draw()
            return
        self.refresh_preview()

    def draw_start(self, event):
        if self.start_zoom_drag(event):
            return
        if self.stamp_mode():
            self.stamp_drag_start(event)
            return
        if self.tool != "redact" or not self.preview_rect or self.busy():
            return
        self.drag_start = self.canvas_point(event)
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.drag_id = self.canvas.create_rectangle(x, y, x, y, outline="#d32f2f", width=2)

    def canvas_point(self, event):
        return (
            max(
                0,
                min(self.preview_rect[0], (self.canvas.canvasx(event.x) - 12) / self.preview_scale),
            ),
            max(
                0,
                min(self.preview_rect[1], (self.canvas.canvasy(event.y) - 12) / self.preview_scale),
            ),
        )

    def draw_move(self, event):
        if self.move_zoom_drag(event):
            return
        if self.stamp_mode():
            self.stamp_drag_move(event)
            return
        if self.drag_start and self.drag_id:
            x, y = self.drag_start
            xx, yy = self.canvas_point(event)
            self.canvas.coords(
                self.drag_id,
                12 + x * self.preview_scale,
                12 + y * self.preview_scale,
                12 + xx * self.preview_scale,
                12 + yy * self.preview_scale,
            )

    def draw_end(self, event):
        if self.end_zoom_drag(event):
            return
        if self.stamp_mode():
            self.stamp_drag_end(event)
            return
        if not self.drag_start:
            return
        x, y = self.drag_start
        xx, yy = self.canvas_point(event)
        self.drag_start = None
        if abs(x - xx) > 3 and abs(y - yy) > 3:
            coords = [min(x, xx), min(y, yy), max(x, xx), max(y, yy)]
            self.regions.setdefault(self.selected_file(), {}).setdefault(
                str(self.page_index), []
            ).append(coords)
        self.refresh_preview()

    def clear_regions(self):
        if self.busy():
            return
        self.regions.get(self.selected_file(), {}).pop(str(self.page_index), None)
        self.refresh_preview()

    def update_region_status(self):
        count = sum(len(rects) for regions in self.regions.values() for rects in regions.values())
        self.region_status.config(text=f"선택 영역 {count}개")
