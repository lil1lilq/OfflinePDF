"""Width-fit document preview, organizer and actual AI comparison."""

from __future__ import annotations

import base64
import math
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pymupdf as pdf

from ..engine import UserError, check_local_path, open_pdf, split_ranges
from ..images import open_image_document
from ..passwords import cached_password
from ..ui import BLUE, MUTED, PANEL


class PreviewController:
    """Width-fit document preview, organizer and actual AI comparison."""

    def toggle_preview(self):
        if self.preview_panel.winfo_manager():
            self.hide_preview()
        else:
            self.show_preview()

    def show_preview(self):
        if self.screen != "preview":
            self.preview_origin = self.capture_preview_origin()
        self.preview_mode = "width"
        self.preview_zoom = 1.0
        self.canvas.xview_moveto(0)
        self.columns.pack_forget()
        self.organizer.pack_forget()
        self.file_overview.pack_forget()
        self.preview_panel.pack(fill="both", expand=True, pady=(8, 0))
        self.preview_button.config(text="미리보기 접기")
        self.schedule_preview()
        if self.work.winfo_manager():
            self.screen = "preview"
        self.update_back_state()

    def hide_preview(self, restore=True):
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
        self.preview_button.config(text="크게 미리보기")
        self.organizer.pack_forget()
        self.file_overview.pack_forget()
        self.columns.pack_forget()
        if self.tool == "extract":
            self.organizer.pack(fill="both", expand=True)
        else:
            self.columns.pack(fill="x", before=self.document_host)
            if self.files:
                self.file_overview.pack(fill="both", expand=True)
                self.overview_title.config(
                    text=Path(self.selected_file()).name if self.selected_file() else ""
                )
                self.overview_detail.config(
                    text=f"{len(self.files)}개 파일이 준비되었습니다. 왼쪽 목록에서 순서와 선택 항목을 확인하세요."
                )
        if self.work.winfo_manager():
            self.screen = "work"
        if origin:
            self.overview_canvas.yview_moveto(origin["overview_y"])
            if self.tool == "extract":
                self.root.after_idle(
                    lambda: self.organizer.scroll_to("moveto", origin["organizer_y"])
                )
            self.schedule_preview()
        self.update_back_state()

    def set_preview_mode(self, mode):
        self.preview_mode = mode
        self.preview_zoom = 1.0
        self.canvas.xview_moveto(0)
        self.refresh_preview()

    def zoom_preview(self, delta):
        self.preview_zoom = max(0.25, min(3.0, self.preview_zoom + delta))
        self.refresh_preview()

    def refresh_organizer(self):
        if self.tool != "extract":
            return
        path = self.selected_file()
        self.organizer.load(path, cached_password(self, path))
        if not self.preview_panel.winfo_manager():
            self.hide_preview()
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
            ttk.Label(cell, text=caption, font=("맑은 고딕", 11, "bold")).pack(anchor="w", pady=5)
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
        if self.screen == "preview":
            self.preview_panel.pack(fill="both", expand=True, pady=(8, 0))
            self.schedule_preview()
        else:
            self.hide_preview(restore=False)
        self.update_back_state()

    def schedule_preview(self):
        if self.preview_timer:
            self.root.after_cancel(self.preview_timer)
        self.preview_timer = self.root.after(250, self.refresh_preview)

    def refresh_preview(self, reset=False):
        self.preview_timer = None
        self.canvas.delete("all")
        self.preview_rect = None
        self.overview_canvas.delete("all")
        if reset:
            self.page_index = 0
            self.canvas.yview_moveto(0)
        path = self.selected_file()
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
            try:
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
                self.page_index = max(0, min(self.page_index, doc.page_count - 1))
                page = doc[self.page_index]
                if self.file_overview.winfo_ismapped():
                    ow = max(150, self.overview_canvas.winfo_width())
                    if (
                        self.tool == "split"
                        and self.options.get("split_mode")
                        and self.options["split_mode"].get() == "N개 파일로 나누기"
                    ):
                        try:
                            ranges = split_ranges(
                                doc.page_count,
                                self.options["split_count"].get(),
                                self.options["split_starts"].get(),
                            )
                            for i, (first, last) in enumerate(ranges):
                                cols = max(1, min(6, int(ow / 180)))
                                cw = ow / cols
                                x = (i % cols) * cw
                                y = (i // cols) * 80
                                self.overview_canvas.create_rectangle(
                                    x + 3, y + 3, x + cw - 8, y + 70, fill=PANEL, outline="#e2e7ef"
                                )
                                self.overview_canvas.create_text(
                                    x + 15, y + 20, anchor="w", text=f"파일 {i + 1:02d}", fill=MUTED
                                )
                                self.overview_canvas.create_text(
                                    x + 15,
                                    y + 47,
                                    anchor="w",
                                    text=f"{first + 1}–{last + 1}쪽",
                                    fill=BLUE,
                                    font=("맑은 고딕", 12, "bold"),
                                )
                            self.overview_canvas.configure(
                                scrollregion=(0, 0, ow, ((len(ranges) + cols - 1) // cols) * 80)
                            )
                        except UserError:
                            pass
                    else:
                        scale = min(
                            (ow - 30) / page.rect.width,
                            math.sqrt(12_000_000 / (page.rect.width * page.rect.height)),
                        )
                        thumb = page.get_pixmap(
                            matrix=pdf.Matrix(max(0.05, scale)), alpha=False, colorspace=pdf.csRGB
                        )
                        self.overview_photo = tk.PhotoImage(
                            data=base64.b64encode(thumb.tobytes("png"))
                        )
                        self.overview_canvas.create_image(
                            ow / 2, 5, anchor="n", image=self.overview_photo
                        )
                        self.overview_canvas.configure(scrollregion=(0, 0, ow, thumb.height + 15))
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
                self.zoom_label.config(
                    text=("폭 맞춤" if self.preview_mode == "width" else "한 페이지")
                    + f" · {round(self.preview_zoom * 100)}%"
                )
                self.page_label.config(text=f"{self.page_index + 1} / {doc.page_count}쪽")
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
                doc.close()
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
        if self.tool == "extract" and self.organizer.model:
            items = self.organizer.model.items
            i = next((j for j, p in enumerate(items) if p[0] == self.organizer_preview_uid), 0)
            self.organizer_preview_uid = items[max(0, min(len(items) - 1, i + delta))][0]
            self.refresh_preview()
            return
        self.page_index = max(0, self.page_index + delta)
        self.refresh_preview()

    def draw_start(self, event):
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
        self.region_status.config(text=f"삭제 영역 {count}개 · 영구 삭제는 한 파일씩 처리합니다.")
