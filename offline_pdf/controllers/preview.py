"""Width-fit document preview, organizer and actual AI comparison."""

from __future__ import annotations

import math
import shutil
import tkinter as tk
from pathlib import Path

from .. import ctk_widgets as ttk
from .. import theme
from ..engine import UserError, check_local_path, pages
from ..overlays import OverlayError
from ..passwords import cached_password
from ..ui import PANEL


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

    def update_preview_controls(self):
        grid = self.active_thumbnail_view()
        self.view_toggle.set("전체 페이지" if grid else "페이지별")
        for widget in (self.single_page_controls, self.preview_nav):
            if grid:
                widget.pack_forget()
            elif not widget.winfo_manager():
                widget.pack(side="right" if widget is self.preview_nav else "left", padx=4)
        for control in self.preview_controls:
            control.configure(
                state="normal" if self.selected_file() and not self.busy() else "disabled"
            )

    def change_page_view(self, value):
        if self.busy():
            self.update_preview_controls()
            return
        if value == "전체 페이지":
            self.show_document_view()
        else:
            self.show_preview()

    def undo_page_edit(self, event=None):
        focus = self.root.focus_get()
        if focus is not None and focus.winfo_class() in ("Entry", "TEntry", "Text"):
            return None
        if self.tool == "extract":
            self.organizer.undo()
            return "break"

    def show_preview(self):
        self.invalidate_preview_render()
        grid = self.active_thumbnail_view()
        if grid:
            self._overview_y = grid.canvas.yview()[0]
            self._overview_path = grid.path
            if grid is self.organizer and grid.model:
                item = next(
                    (p for p in grid.model.items if p[0] in grid.model.selected),
                    grid.model.items[0],
                )
                self.organizer_preview_uid = item[0]
        self.organizer.pack_forget()
        self.overview.pack_forget()
        self.split_view.pack_forget()
        self.show_preview_toolbar()
        if self.tool == "extract" or self.settings_panel_needed():
            self.columns.pack(fill="x", before=self.document_host)
        else:
            self.columns.pack_forget()
        self.preview_panel.pack(fill="both", expand=True, pady=(8, 0))
        self.preview_mode = "width"
        self.preview_zoom = 1.0
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        if self.work.winfo_manager():
            self.screen = "preview" if self.tool == "extract" else "work"
        self.update_preview_controls()
        self.schedule_preview()
        self.update_back_state()

    def show_document_view(self, restore=True):
        self.invalidate_preview_render()
        self.show_preview_toolbar()
        self.preview_panel.pack_forget()
        self.organizer.pack_forget()
        self.overview.pack_forget()
        self.split_view.pack_forget()
        if self.tool == "extract" or self.settings_panel_needed():
            self.columns.pack(fill="x", before=self.document_host)
        else:
            self.columns.pack_forget()
        grid = self.organizer if self.tool == "extract" else self.overview
        try:
            grid.load(self.selected_file(), cached_password(self, self.selected_file()))
        except (UserError, OverlayError) as exc:
            self.status.set(str(exc))
        if grid is self.overview and grid.model and self.page_index < len(grid.model.items):
            grid.model.selected = {grid.model.items[self.page_index][0]}
        grid.pack(fill="both", expand=True)
        grid.draw()
        if restore and grid.path == getattr(self, "_overview_path", None):
            self.root.after_idle(lambda: grid.scroll_to("moveto", getattr(self, "_overview_y", 0)))
        if self.work.winfo_manager():
            self.screen = "work"
        self.update_preview_controls()
        self.update_back_state()

    def set_preview_mode(self, mode):
        if self.active_thumbnail_view() or not self.ensure_preview_visible():
            return
        self.preview_mode = mode
        self.preview_zoom = 1.0
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.refresh_preview()

    def set_preview_percent(self, event=None):
        if self.active_thumbnail_view():
            return "break"
        try:
            value = float(self.zoom_value.get().strip().rstrip("%")) / 100
            if abs(value - self.preview_scale) < 0.0051:
                return "break"
            if not math.isfinite(value) or not 0.1 <= value <= 5:
                raise ValueError()
        except ValueError:
            self.zoom_value.set(f"{round(self.preview_scale * 100)}%")
            return "break"
        self.preview_mode = "custom"
        self.preview_zoom = value
        self.refresh_preview()
        return "break"

    def zoom_preview(self, delta):
        if self.active_thumbnail_view() or not self.ensure_preview_visible():
            return
        self.preview_zoom = max(0.1, min(5.0, self.preview_scale + delta))
        self.preview_mode = "custom"
        self.refresh_preview()

    def active_thumbnail_view(self):
        for view in (self.organizer, self.overview):
            if view.winfo_manager():
                return view
        return None

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
        self.invalidate_preview_render()
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

    def invalidate_preview_render(self):
        renderer = getattr(self, "_viewport_renderer", None)
        if renderer is not None:
            renderer.invalidate()
        self._prepared_preview = None
        self.preview_rect = None
        self._crop_handles = {}
        self._crop_drag = None
        self._stamp_box = None
        self._stamp_drag = None
        self._viewport_signature = None
        self._sharp_viewport_revision = None

    def close_preview_render(self):
        self.invalidate_preview_render()
        if self.preview_timer:
            self.root.after_cancel(self.preview_timer)
            self.preview_timer = None
        if getattr(self, "_viewport_timer", None):
            self.root.after_cancel(self._viewport_timer)
            self._viewport_timer = None
        if getattr(self, "_viewport_renderer", None):
            self._viewport_renderer.close()
            self._viewport_renderer = None
        if getattr(self, "_preview_cache", None):
            self._preview_cache.close()

    def preview_scroll_changed(self, axis, first, last):
        bar = self.preview_vscroll if axis == "y" else self.preview_hscroll
        bar.set(first, last)
        if not getattr(self, "_preview_refreshing", False):
            self.paint_preview_viewport()

    def preview_scroll(self, axis, *args):
        (self.canvas.yview if axis == "y" else self.canvas.xview)(*args)
        self.paint_preview_viewport()

    def paint_preview_viewport(self):
        from PIL import Image, ImageTk

        from ..preview_render import ViewportRenderer, visible_pixels

        entry = getattr(self, "_prepared_preview", None)
        if (
            entry is None
            or self.active_thumbnail_view()
            or not self.preview_panel.winfo_manager()
            or getattr(self, "_painting_viewport", False)
        ):
            return
        width, height = self.preview_rect
        pixels = visible_pixels(
            (width * self.preview_scale, height * self.preview_scale),
            (self.canvas.canvasx(0), self.canvas.canvasy(0)),
            (self.canvas.winfo_width(), self.canvas.winfo_height()),
        )
        signature = (entry.token, self.preview_scale, pixels)
        if signature == getattr(self, "_viewport_signature", None):
            return
        self._painting_viewport = True
        try:
            self._viewport_signature = signature
            base = entry.thumbnail()
            x0, y0, x1, y1 = pixels
            source_rect = (
                x0 / (width * self.preview_scale) * base.width,
                y0 / (height * self.preview_scale) * base.height,
                x1 / (width * self.preview_scale) * base.width,
                y1 / (height * self.preview_scale) * base.height,
            )
            picture = base.transform(
                (x1 - x0, y1 - y0),
                Image.Transform.EXTENT,
                source_rect,
                Image.Resampling.BILINEAR,
                fillcolor=(255, 255, 255),
            )
            try:
                photo = ImageTk.PhotoImage(picture, master=self.root)
            finally:
                picture.close()
            self.canvas.delete("preview_raster")
            self.preview_photo = photo
            self.canvas.create_image(
                12 + x0, 12 + y0, anchor="nw", image=photo, tags="preview_raster"
            )
            self.canvas.tag_lower("preview_raster")
            renderer = getattr(self, "_viewport_renderer", None)
            if (
                renderer is not None
                and renderer.process.pid is not None
                and not renderer.process.is_alive()
            ):
                renderer.close()
                renderer = None
            if renderer is None:
                renderer = self._viewport_renderer = ViewportRenderer()
            try:
                self._viewport_revision = renderer.submit(entry, self.preview_scale, pixels)
            except (OSError, RuntimeError):
                renderer.close()
                self._viewport_renderer = None
                self.status.set(
                    "선명한 미리보기를 표시하지 못했습니다. 페이지를 다시 선택해 주세요."
                )
                return
            if not getattr(self, "_viewport_timer", None):
                self._viewport_timer = self.root.after(16, self.poll_preview_raster)
            if self.stamp_mode() and getattr(self, "_stamp_box", None):
                self.draw_stamp_layer()
        finally:
            self._painting_viewport = False

    def poll_preview_raster(self):
        from PIL import Image, ImageTk

        self._viewport_timer = None
        renderer = getattr(self, "_viewport_renderer", None)
        if renderer is None:
            return
        result = renderer.poll()
        if result is not None and result[0] == getattr(self, "_viewport_revision", None):
            raster = result[1]
            if (
                raster is not None
                and self._prepared_preview is not None
                and self.preview_panel.winfo_manager()
                and self.work.winfo_manager()
            ):
                x, y, width, height, samples = raster
                with Image.frombytes("RGB", (width, height), samples) as picture:
                    photo = ImageTk.PhotoImage(picture, master=self.root)
                self.canvas.delete("preview_raster")
                self.preview_photo = photo
                self.canvas.create_image(
                    12 + x, 12 + y, anchor="nw", image=photo, tags="preview_raster"
                )
                self.canvas.tag_lower("preview_raster")
                self._sharp_viewport_revision = result[0]
            elif raster is None and self.preview_panel.winfo_manager():
                self.status.set(
                    "선명한 미리보기를 표시하지 못했습니다. 페이지를 다시 선택해 주세요."
                )
        if renderer.pending:
            self._viewport_timer = self.root.after(16, self.poll_preview_raster)

    def refresh_preview(self, reset=False):
        self._preview_refreshing = True
        try:
            self._refresh_preview(reset)
        finally:
            self._preview_refreshing = False

    def _refresh_preview(self, reset=False):
        if self.preview_timer:
            self.root.after_cancel(self.preview_timer)
        self.preview_timer = None
        self.invalidate_preview_render()
        self.canvas.delete("all")
        self.preview_rect = None
        self._crop_box = None
        self._crop_drag = None
        self._crop_handles = {}
        self._stamp_box = None
        self._stamp_drag = None
        self.canvas.config(cursor="")
        if not self.work.winfo_manager():
            self.close_preview_render()
            self.preview_photo = None
            return
        if reset:
            self.page_index = 0
            self.canvas.yview_moveto(0)
        path = self.selected_file()
        if not path:
            self.close_preview_render()
            self.preview_photo = None
        grid = self.active_thumbnail_view()
        if grid:
            try:
                grid.load(path, cached_password(self, path))
            except (UserError, OverlayError) as exc:
                self.status.set(str(exc))
            grid.cache.clear()
            grid.draw()
            return
        if not path:
            if getattr(self, "_preview_cache", None):
                self._preview_cache.close()
            self.canvas.config(scrollregion=(0, 0, max(300, self.canvas.winfo_width()), 280))
            self.page_label.config(text="미리보기")
            return
        try:
            check_local_path(path)
            password = cached_password(self, path)
            from ..preview_render import PreviewCache

            if not getattr(self, "_preview_cache", None):
                self._preview_cache = PreviewCache()
            doc = self._preview_cache.document(path, password)
            nup_doc = None
            preview_total = doc.page_count
            preview_index = None
            if self.tool == "nup":
                from ..nup import NupLayout

                options = {key: value.get() for key, value in self.options.items()}
                selected = pages(options.get("pages", ""), doc.page_count, duplicates=True)
                layout = NupLayout.from_options(options, doc[selected[0]].rect)
                preview_total = math.ceil(len(selected) / layout.count)
                self.page_index = max(0, min(self.page_index, preview_total - 1))
                preview_index = self.page_index
                entry = self._preview_cache.prepared(
                    preview_index, nup_options=options, selected=selected
                )
                nup_doc = entry.document
            angle = 0
            if self.tool == "extract" and self.organizer.model:
                item = next(
                    (p for p in self.organizer.model.items if p[0] == self.organizer_preview_uid),
                    self.organizer.model.items[0],
                )
                self.organizer_preview_uid = item[0]
                self.page_index = item[1]
                angle = item[2]
            if nup_doc is None:
                self.page_index = max(0, min(self.page_index, doc.page_count - 1))
            if nup_doc is None:
                number_options = (
                    {key: value.get() for key, value in self.options.items()}
                    if self.tool == "number"
                    else None
                )
                entry = self._preview_cache.prepared(
                    self.page_index, angle, number_options=number_options
                )
            page = entry.page
            crop_rect = None
            if self.tool == "crop":
                options = {key: value.get() for key, value in self.options.items()}
                from ..crop import crop_pages, visible_crop_rect

                options["crop_page"] = self.page_index + 1
                chosen = crop_pages(options, doc.page_count)
                if self.page_index in chosen:
                    crop_rect = visible_crop_rect(page, options)
            rw, rh = page.rect.width, page.rect.height
            w = max(self.canvas.winfo_width() - 24, 150)
            h = max(100, self.canvas.winfo_height() - 24)
            fit = (
                min(w / rw, h / rh)
                if self.preview_mode == "page"
                else h / rh
                if self.preview_mode == "height"
                else w / rw
            )
            requested = self.preview_zoom if self.preview_mode == "custom" else fit
            self.preview_scale = min(requested, 20_000 / rh)
            self.preview_rect = (rw, rh)
            self.canvas.configure(
                scrollregion=(
                    0,
                    0,
                    math.ceil(rw * self.preview_scale) + 24,
                    math.ceil(rh * self.preview_scale) + 24,
                )
            )
            self._prepared_preview = entry
            self.paint_preview_viewport()
            if crop_rect is not None:
                self._crop_box = tuple(crop_rect)
                self.draw_crop_overlay()
            self.zoom_value.set(f"{round(self.preview_scale * 100)}%")
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
                self.page_label.config(text=f"{position + 1} / {len(self.organizer.model.items)}쪽")
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
        number = getattr(event, "num", None)
        delta = getattr(event, "delta", 0)
        if number in (4, 5):
            step = -1 if number == 4 else 1
        elif delta:
            step = -1 if delta > 0 else 1
        else:
            return "break"
        if getattr(event, "state", 0) & 4:
            # Consume modified wheels so zoom does not also scroll the page.
            if (
                not self.busy()
                and self.preview_rect
                and not self.drag_start
                and not getattr(self, "_stamp_drag", None)
                and not getattr(self, "_crop_drag", None)
            ):
                factor = 1.1 if step < 0 else 1 / 1.1
                self.zoom_preview(self.preview_scale * (factor - 1))
            return "break"
        self.canvas.yview_scroll(step * 3, "units")
        self.paint_preview_viewport()
        return "break"

    def turn(self, delta):
        if self.active_thumbnail_view():
            return
        if not self.ensure_preview_visible():
            return
        if self.tool == "extract" and self.organizer.model:
            items = self.organizer.model.items
            i = next((j for j, p in enumerate(items) if p[0] == self.organizer_preview_uid), 0)
            self.organizer_preview_uid = items[max(0, min(len(items) - 1, i + delta))][0]
            self.refresh_preview()
            return
        self.page_index = max(0, self.page_index + delta)
        self.refresh_preview()

    def draw_start(self, event):
        if self.busy() or getattr(event, "state", 0) & 4:
            return
        if self.tool == "crop":
            self.crop_drag_start(event)
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
        if self.tool == "crop":
            self.crop_drag_move(event)
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
        if self.tool == "crop":
            self.crop_drag_end(event)
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
