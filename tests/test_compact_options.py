"""User flows for compact pickers, live options, split scope and file order."""

import tempfile
import time
import tkinter as tk
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import customtkinter as ctk
import pymupdf as pdf

from offline_pdf.app import App
from offline_pdf.compact_controls import ChoicePopup, picker_position
from offline_pdf.localization import apply_language
from offline_pdf.overlays import POSITIONS
from offline_pdf.tools import TOOLS
from offline_pdf.windows_drop import NativeFileDrop


class PickerPositionTests(unittest.TestCase):
    def test_secondary_monitors_edges_and_dpi_sizes(self):
        cases = [
            ((2500, 200, 2650, 236), (300, 160), (1920, 0, 3840, 1040), (2500, 236)),
            ((-1400, 300, -1250, 336), (300, 160), (-1920, 0, 0, 1080), (-1400, 336)),
            ((400, -600, 550, -564), (300, 160), (0, -1080, 1920, 0), (400, -564)),
            ((-500, -200, -350, -164), (300, 160), (-1600, -900, -320, -100), (-620, -360)),
            ((1850, 1000, 1900, 1036), (300, 160), (0, 0, 1920, 1040), (1620, 840)),
            ((-200, 800, -100, 836), (300, 160), (-1920, 0, 0, 1040), (-300, 836)),
            ((-200, 800, -100, 836), (450, 240), (-1920, 0, 0, 1040), (-450, 560)),
            ((0, 0, 50, 36), (300, 160), (0, 0, 200, 100), (0, 0)),
        ]
        for anchor, size, bounds, expected in cases:
            with self.subTest(anchor=anchor, size=size):
                self.assertEqual(picker_position(anchor, size, bounds), expected)

    def test_popup_uses_absolute_negative_coordinates_and_ignores_child_resize(self):
        popup = Mock()
        popup.winfo_reqwidth.return_value = 300
        popup.winfo_reqheight.return_value = 160
        popup.winfo_rootx.return_value = 0
        popup.winfo_rooty.return_value = 0
        picker = SimpleNamespace(
            popup=popup,
            winfo_rootx=lambda: -1400,
            winfo_rooty=lambda: -600,
            winfo_width=lambda: 150,
            winfo_height=lambda: 36,
        )
        with patch(
            "offline_pdf.compact_controls.monitor_work_area", return_value=(-1920, -1080, 0, 0)
        ):
            ChoicePopup.position_picker(picker)
        popup.geometry.assert_called_once_with("+-1400+-564")
        popup.geometry.reset_mock()
        ChoicePopup.position_picker(picker, SimpleNamespace(widget=object()))
        popup.geometry.assert_not_called()

    def test_monitor_query_failure_uses_owner_bounds(self):
        popup = Mock()
        popup.winfo_reqwidth.return_value = 300
        popup.winfo_reqheight.return_value = 160
        popup.winfo_rootx.return_value = 0
        popup.winfo_rooty.return_value = 0
        owner = SimpleNamespace(
            winfo_rootx=lambda: 2000,
            winfo_rooty=lambda: 100,
            winfo_width=lambda: 1000,
            winfo_height=lambda: 800,
        )
        picker = SimpleNamespace(
            popup=popup,
            winfo_rootx=lambda: 2200,
            winfo_rooty=lambda: 200,
            winfo_width=lambda: 150,
            winfo_height=lambda: 36,
            winfo_toplevel=lambda: owner,
        )
        with patch("offline_pdf.compact_controls.monitor_work_area", return_value=None):
            ChoicePopup.position_picker(picker)
        popup.geometry.assert_called_once_with("+2200+236")


class CompactOptionsTests(unittest.TestCase):
    def pump(self, seconds=0.4):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)

    def setUp(self):
        try:
            self.root = ctk.CTk()
        except tk.TclError:
            self.skipTest("GUI requires a display")
        self.root.geometry("1200x850")
        self.app = App(self.root)
        self.app.auto_open.set(False)
        self.temp = tempfile.TemporaryDirectory()
        self.files = []
        for i in range(3):
            path = Path(self.temp.name) / f"document-{i}.pdf"
            with pdf.open() as doc:
                for j in range(5):
                    doc.new_page().insert_text((72, 72), f"Document {i} page {j}")
                doc.save(path)
            self.files.append(str(path.resolve()))
        self.app.add_paths(self.files)
        self.root.update()
        self.root.report_callback_exception = self.callback_error

    def callback_error(self, exc, value, traceback):
        raise value.with_traceback(traceback)

    def tearDown(self):
        if hasattr(self, "app"):
            apply_language(self.root, "ko")
            self.app.close()
            self.temp.cleanup()

    def test_position_picker_preserves_preview_space_and_canonical_values(self):
        self.app.select_tool("number")
        self.app.show_preview()
        self.root.update()
        self.assertTrue(self.app.columns.winfo_ismapped())
        height = self.app.columns.winfo_height()
        picker = self.app.option_widgets["number_position"]
        picker.invoke()
        self.root.update()
        buttons = picker.popup.winfo_children()[0].winfo_children()
        self.assertEqual(len(buttons), 9)
        for button in buttons:
            name = button.source_text
            x, y = POSITIONS[name]
            self.assertEqual(int(button.grid_info()["column"]), int(x * 2))
            self.assertEqual(int(button.grid_info()["row"]), int(y * 2))
        self.assertEqual(self.app.columns.winfo_height(), height)
        picker.choose("왼쪽 가운데")
        self.root.update()
        self.assertEqual(self.app.options["number_position"].get(), "왼쪽 가운데")
        self.assertIsNone(picker.popup)
        picker.invoke()
        self.root.update()
        self.root.event_generate("<ButtonPress-1>", x=5, y=5)
        self.root.update()
        self.assertIsNone(picker.popup)
        self.app.home_button.invoke()
        self.root.update()
        self.assertEqual(self.app.screen, "home")
        self.app.select_tool("watermark")
        apply_language(self.root, "en")
        self.app.option_widgets["position"].choose("왼쪽 가운데")
        self.assertEqual(self.app.options["position"].get(), "왼쪽 가운데")
        self.app.option_widgets["insert_mode"].set("이미지")
        self.assertTrue(self.app.stamp_mode())
        self.assertEqual(self.app.option_widgets["insert_mode"].get(), "Image")
        self.app.option_widgets["position"].invoke()
        self.root.update()
        self.app.select_tool("merge")  # also destroys any open popup and its traces
        self.root.update()
        self.assertIsNone(getattr(self.root, "_option_picker", None))

    def test_empty_split_screen_shows_document_after_import_without_reentry(self):
        self.app.clear_files()
        self.app.select_tool("split")
        self.root.update()
        self.assertTrue(self.app.preview_zoom_row.winfo_ismapped())
        self.assertTrue(self.app.split_view.winfo_ismapped())
        self.assertTrue(
            all(button.cget("state") == "disabled" for button in self.app.preview_controls)
        )
        self.app.add_paths([self.files[0]])
        self.pump()
        self.assertTrue(self.app.split_view.winfo_ismapped())
        self.assertTrue(
            any(
                self.app.split_view.canvas.type(item) == "image"
                for item in self.app.split_view.canvas.find_all()
            )
        )
        self.assertIsNotNone(self.app.split_view.doc)
        self.assertTrue(
            all(button.cget("state") == "normal" for button in self.app.preview_controls)
        )
        self.assertFalse(self.app.single_page_controls.winfo_ismapped())
        self.assertFalse(self.app.preview_nav.winfo_ismapped())
        self.app.add_paths([self.files[1]])
        self.root.update()
        self.assertTrue(self.app.split_view.winfo_ismapped())
        self.assertEqual(self.app.screen, "work")

    def test_toolbar_available_in_every_tool_and_fit_controls_work_in_single_view(self):
        for tool in TOOLS:
            with self.subTest(tool=tool):
                self.app.select_tool(tool)
                self.root.update()
                self.assertTrue(self.app.preview_zoom_row.winfo_ismapped())
                self.assertEqual(
                    bool(self.app.preview_nav.winfo_ismapped()), self.app.tool != "extract"
                )
        self.app.select_tool("number")
        self.root.update()
        self.assertTrue(self.app.preview_panel.winfo_ismapped())
        self.app.set_preview_mode("page")
        self.root.update()
        self.assertTrue(self.app.preview_panel.winfo_ismapped())
        self.assertEqual(self.app.preview_mode, "page")
        self.assertEqual(self.app.screen, "work")
        self.assertFalse(hasattr(self.app, "preview_button"))
        scale = self.app.preview_scale
        self.app.zoom_preview(0.25)
        self.assertAlmostEqual(self.app.preview_zoom, scale + 0.25)
        self.assertTrue(self.app.preview_panel.winfo_manager())

    def test_every_tool_can_switch_grid_double_click_page_and_restore_scroll(self):
        for tool in TOOLS:
            with self.subTest(tool=tool):
                self.app.select_tool(tool)
                self.app.show_document_view()
                self.pump(0.08)
                view = self.app.active_thumbnail_view()
                self.assertIsNotNone(view)
                self.assertFalse(self.app.single_page_controls.winfo_ismapped())
                width = view.tile_width.get()
                self.app.set_preview_mode("width")
                self.app.zoom_preview(1)
                self.assertEqual(view.tile_width.get(), width)
                event = SimpleNamespace(x=50, y=80, state=0)
                view.double_click(event)
                self.pump(0.08)
                self.assertIsNone(self.app.active_thumbnail_view())
                self.assertTrue(self.app.single_page_controls.winfo_ismapped())
                self.assertEqual(self.app.preview_mode, "width")
                self.app.show_document_view()
                self.pump(0.08)
                self.assertIs(self.app.active_thumbnail_view(), view)

    def test_percent_is_absolute_and_height_fit_uses_actual_pdf_dimensions(self):
        self.app.select_tool("number")
        self.pump()
        self.app.set_preview_mode("width")
        expected = max(self.app.canvas.winfo_width() - 24, 150) / 595
        self.assertAlmostEqual(self.app.preview_scale, expected, places=3)
        self.app.zoom_value.set("150%")
        self.app.set_preview_percent()
        self.assertAlmostEqual(self.app.preview_scale, 1.5)
        self.app.zoom_preview(-0.1)
        self.assertAlmostEqual(self.app.preview_scale, 1.4)
        self.app.set_preview_mode("height")
        self.assertAlmostEqual(
            self.app.preview_scale, max(100, self.app.canvas.winfo_height() - 24) / 842, places=3
        )
        previous = self.app.preview_scale
        for invalid in ("NaN", "0%", "99999%", "text"):
            self.app.zoom_value.set(invalid)
            self.app.set_preview_percent()
            self.assertEqual(self.app.preview_scale, previous)

    def test_cut_and_checkbox_double_click_do_not_open_page(self):
        self.app.select_tool("extract")
        self.pump()
        view = self.app.organizer
        x0, y0, x1, y1 = view.separators[1]
        event = SimpleNamespace(x=(x0 + x1) / 2, y=(y0 + y1) / 2 - view.canvas.canvasy(0), state=0)
        view.press(event)
        view.release(event)
        view.double_click(event)
        self.assertIs(self.app.active_thumbnail_view(), view)

        self.assertEqual(view.model.cuts(), {1})
        event = SimpleNamespace(x=24, y=view.cellh - 34, state=0)
        view.press(event)
        view.release(event)
        selection = set(view.model.selected)
        view.double_click(event)
        self.assertEqual(view.model.selected, selection)
        self.assertIs(self.app.active_thumbnail_view(), view)

    def test_grid_scroll_selection_and_cuts_survive_single_page_view(self):
        self.app.select_tool("extract")
        self.pump()
        view = self.app.organizer
        view.model.set_cuts({2})
        view.model.selected = {view.model.items[3][0]}
        view.scroll_to("moveto", 0.5)
        self.pump()
        y = view.canvas.yview()[0]
        selected = set(view.model.selected)
        view.enlarge()
        self.pump()
        self.assertEqual(self.app.page_index, 3)
        self.app.show_document_view()
        self.pump()
        self.assertEqual(view.model.selected, selected)
        self.assertEqual(view.model.cuts(), {2})
        self.assertAlmostEqual(view.canvas.yview()[0], y, places=2)

    def test_split_settings_interval_and_undo(self):
        self.app.select_tool("extract")
        self.pump()
        view = self.app.organizer
        dialog = view.split_settings()
        self.root.update()
        body = dialog.winfo_children()[0]
        row = next(w for w in body.winfo_children() if isinstance(w, ctk.CTkFrame))
        next(w for w in row.winfo_children() if isinstance(w, ctk.CTkButton)).invoke()
        self.root.update()
        self.assertEqual(view.model.cuts(), {1, 2, 3, 4})
        self.assertIn("PDF 5개로 나눠 저장", self.app.run_button.source_text)
        view.undo()
        self.assertEqual(view.model.cuts(), set())

    def test_nup_overview_counts_output_sheets_and_renders_crop_and_number(self):
        for tool in ("nup", "crop", "number"):
            self.app.select_tool(tool)
            if tool == "nup":
                self.app.options["nup_count"].set("2")
            self.app.show_document_view()
            self.pump()
            view = self.app.overview
            page, temporary = view.thumbnail_page(0)
            try:
                self.assertGreater(page.rect.width, 0)
                self.assertTrue(
                    any(view.canvas.type(item) == "image" for item in view.canvas.find_all())
                )
            finally:
                temporary.close()
            if tool == "nup":
                self.assertEqual(len(view.model.items), 3)

    def test_split_boundaries_toggle_on_click_and_saved_ranges_match(self):
        self.app.select_tool("split")
        self.pump()
        view = self.app.split_view
        self.assertEqual(len(view.model.items), 5)
        self.assertEqual(view.model.cuts(), set())
        self.assertEqual(self.app.run_button.cget("state"), "normal")
        for boundary in (1, view.columns):
            if boundary >= 5:
                continue
            with self.subTest(boundary=boundary):
                x0, y0, x1, y1 = view.separators[boundary]
                x, y = (x0 + x1) / 2, (y0 + y1) / 2 - view.canvas.canvasy(0)
                event = SimpleNamespace(x=x, y=y, state=0)
                view.press(event)
                view.release(event)
                self.assertIn(boundary, view.model.cuts())
                self.assertTrue(view.canvas.find_withtag("cut_scissors"))
                view.press(event)
                view.release(event)
                self.assertNotIn(boundary, view.model.cuts())
        view.model.set_cuts({1, 3})
        self.assertEqual(len(view.model.segments()), 3)
        from offline_pdf.engine import execute

        before = Path(self.files[0]).read_bytes()
        folder = execute(
            {
                "tool": "extract",
                "files": self.app.active_job_files(),
                "output": self.temp.name,
                "options": {"page_plan": view.model.plan(), "page_cuts": sorted(view.model.cuts())},
            }
        )
        counts = []
        for path in sorted(folder.glob("*.pdf")):
            with pdf.open(path) as doc:
                counts.append(doc.page_count)
        self.assertEqual(counts, [1, 2, 2])
        self.assertEqual(Path(self.files[0]).read_bytes(), before)
        self.app.file_list.selection_clear(0, "end")
        self.app.file_list.selection_set(1)
        self.app.file_selected()
        self.pump()
        self.assertEqual(view.model.cuts(), set())

    def test_split_grid_can_scroll_to_last_page_without_rendering_all_at_once(self):
        source = Path(self.temp.name) / "many-pages.pdf"
        with pdf.open() as doc:
            for _ in range(100):
                doc.new_page()
            doc.save(source)
        self.app.clear_files()
        self.app.select_tool("split")
        self.app.add_paths([str(source)])
        self.pump()
        view = self.app.split_view
        self.assertEqual(len(view.model.items), 100)
        self.assertLess(len(view.canvas.find_withtag("cut_line")), 99)
        view.scroll_to("moveto", 1)
        self.pump()
        self.assertIn(99, view.separators)
        self.assertNotIn(100, view.separators)
        self.assertLessEqual(len(view.cache), 64)

    def set_crop_margins(self, value):
        for side in ("left", "top", "right", "bottom"):
            self.app.options[f"margin_{side}"].set(value)

    def test_crop_handles_update_only_overlays_and_keep_mm_values_in_save(self):
        from offline_pdf.crop import MM
        from offline_pdf.engine import execute

        self.app.select_tool("crop")
        self.app.options["margin_top"].set("10.1234")
        self.pump()
        self.app.set_preview_mode("height")
        self.assertEqual(len(self.app.canvas.find_withtag("crop_handle")), 8)
        x, y = self.app._crop_handles["w"]
        event = SimpleNamespace(
            x=x - self.app.canvas.canvasx(0), y=y - self.app.canvas.canvasy(0), state=0
        )
        self.app.preview_hover(event)
        self.assertEqual(self.app.canvas.cget("cursor"), "hand2")
        photo = self.app.preview_photo
        scale = self.app.preview_scale
        self.app.draw_start(event)
        end = SimpleNamespace(x=event.x + 5 * MM * scale, y=event.y, state=0)
        self.app.draw_move(end)
        self.assertIs(self.app.preview_photo, photo)
        self.assertAlmostEqual(
            float(self.app.options["margin_left"].get()), 15, delta=0.011 + 1 / (MM * scale)
        )
        self.assertEqual(self.app.options["margin_top"].get(), "10.1234")
        self.app.preview_wheel(SimpleNamespace(delta=120, state=4))
        self.assertEqual(self.app.preview_scale, scale)
        self.app.draw_end(end)
        self.assertIsNone(self.app._crop_drag)
        options = {key: value.get() for key, value in self.app.options.items()}
        folder = execute(
            {"tool": "crop", "files": [self.files[0]], "output": self.temp.name, "options": options}
        )
        with pdf.open(next(folder.glob("*.pdf"))) as doc:
            self.assertAlmostEqual(doc[0].cropbox.x0, float(options["margin_left"]) * MM, places=3)
        self.app.crop_reset()
        self.assertTrue(
            all(
                self.app.options[f"margin_{side}"].get() == "0"
                for side in ("left", "top", "right", "bottom")
            )
        )
        self.assertFalse(self.app.canvas.find_withtag("crop_shade"))
        self.assertEqual(len(self.app.canvas.find_withtag("crop_handle")), 8)
        self.app.show_document_view()
        self.assertIsNotNone(self.app.active_thumbnail_view())
        self.assertIsNone(self.app.crop_handle_at(event))

    def test_crop_scope_selects_job_files_and_updates_page_controls(self):
        self.app.select_tool("crop")
        self.pump()
        self.assertEqual(self.app.active_job_files(), self.files)
        self.assertFalse(self.app.option_widgets["pages"].winfo_ismapped())
        self.app.options["crop_scope"].set("현재 페이지")
        self.app.page_index = 2
        self.app.refresh_preview()
        self.assertEqual(self.app.active_job_files(), [self.files[0]])
        self.assertEqual(len(self.app.canvas.find_withtag("crop_handle")), 8)
        self.app.options["crop_scope"].set("지정 페이지")
        self.app.options["pages"].set("2")
        self.app.refresh_preview()
        self.root.update()
        self.assertTrue(self.app.option_widgets["pages"].winfo_ismapped())
        self.assertFalse(self.app.canvas.find_withtag("crop_handle"))
        self.app.page_index = 1
        self.app.refresh_preview()
        self.assertEqual(len(self.app.canvas.find_withtag("crop_handle")), 8)

    def test_crop_shading_follows_pages_margin_and_saved_crop_box(self):
        from offline_pdf.engine import execute

        self.app.select_tool("crop")
        self.app.options["crop_scope"].set("지정 페이지")
        self.app.options["pages"].set("2")
        self.set_crop_margins("5")
        self.root.update()
        self.app.refresh_preview(reset=True)
        self.assertFalse(self.app.canvas.find_withtag("crop_shade"))
        self.app.turn(1)
        self.assertEqual(len(self.app.canvas.find_withtag("crop_shade")), 4)
        boundary = self.app.canvas.find_withtag("crop_boundary")[0]
        inset = 5 * 72 / 25.4
        self.assertAlmostEqual(
            self.app.canvas.coords(boundary)[0], 12 + inset * self.app.preview_scale
        )
        before = Path(self.files[0]).read_bytes()
        folder = execute(
            {
                "tool": "crop",
                "files": [self.files[0]],
                "output": self.temp.name,
                "options": {key: value.get() for key, value in self.app.options.items()},
            }
        )
        with pdf.open(next(folder.glob("*.pdf"))) as doc:
            self.assertEqual(doc[0].cropbox, doc[0].mediabox)
            self.assertAlmostEqual(doc[1].cropbox.x0, inset, places=3)
            self.assertAlmostEqual(
                doc[1].cropbox.width, doc[1].mediabox.width - 2 * inset, places=3
            )
        self.assertEqual(Path(self.files[0]).read_bytes(), before)
        self.set_crop_margins("0")
        self.app.refresh_preview()
        self.assertFalse(self.app.canvas.find_withtag("crop_shade"))
        self.set_crop_margins("invalid")
        self.app.refresh_preview()
        self.assertIsNone(self.app.preview_rect)
        self.assertEqual(self.app.page_label.cget("text"), "설정을 확인하세요")

    def test_crop_shading_handles_rotated_previously_cropped_pages(self):
        source = Path(self.temp.name) / "rotated-crop.pdf"
        with pdf.open() as doc:
            for rotation in (0, 90, 180, 270):
                page = doc.new_page(width=480, height=640)
                page.set_cropbox(pdf.Rect(15, 25, 450, 610))
                page.set_rotation(rotation)
            doc.save(source)
        self.app.clear_files()
        self.app.select_tool("crop")
        self.app.add_paths([str(source)])
        self.set_crop_margins("7")
        self.root.update()
        for index in range(4):
            self.app.page_index = index
            self.app.refresh_preview()
            with self.subTest(index=index):
                self.assertEqual(len(self.app.canvas.find_withtag("crop_shade")), 4)
                boundary = self.app.canvas.find_withtag("crop_boundary")[0]
                inset = 7 * 72 / 25.4 * self.app.preview_scale
                self.assertAlmostEqual(self.app.canvas.coords(boundary)[0], 12 + inset)
                self.assertAlmostEqual(self.app.canvas.coords(boundary)[1], 12 + inset)
        self.set_crop_margins("100")
        self.app.refresh_preview()
        self.assertFalse(self.app.canvas.find_withtag("crop_shade"))
        self.assertIsNone(self.app.preview_rect)

    def test_two_button_view_toggle_switches_and_keeps_selection_in_english(self):
        self.app.select_tool("number")
        self.pump()
        toggle = self.app.view_toggle
        self.assertIsInstance(toggle, ctk.CTkSegmentedButton)
        self.assertEqual(toggle.get(), "페이지별")
        toggle._buttons_dict["전체 페이지"].invoke()
        self.pump()
        self.assertIsNotNone(self.app.active_thumbnail_view())
        self.assertEqual(toggle.get(), "전체 페이지")
        apply_language(self.root, "en")
        self.root.update()
        self.assertEqual(toggle.get(), "All pages")
        toggle._buttons_dict["Single page"].invoke()
        self.pump()
        self.assertIsNone(self.app.active_thumbnail_view())
        self.assertEqual(toggle.get(), "Single page")
        with patch.object(self.app, "busy", return_value=True):
            toggle._buttons_dict["All pages"].invoke()
            self.assertEqual(toggle.get(), "Single page")

    def test_control_wheel_zooms_without_scroll_or_edits_and_plain_wheel_scrolls(self):
        self.app.select_tool("redact")
        self.pump()
        self.app.set_preview_mode("width")
        self.app.canvas.yview_moveto(0)
        scale = self.app.preview_scale
        self.app.canvas.event_generate("<MouseWheel>", delta=120, state=4)
        self.root.update()
        self.assertAlmostEqual(self.app.preview_scale, scale + 0.1)
        self.assertEqual(self.app.preview_mode, "custom")
        self.assertAlmostEqual(self.app.canvas.yview()[0], 0)
        self.assertEqual(self.app.regions, {})
        self.app.canvas.event_generate("<MouseWheel>", delta=-120, state=4)
        self.root.update()
        self.assertAlmostEqual(self.app.preview_scale, scale)
        self.app.preview_wheel(SimpleNamespace(num=4, delta=0, state=4))
        self.assertAlmostEqual(self.app.preview_scale, scale + 0.1)
        self.app.preview_wheel(SimpleNamespace(num=5, delta=0, state=4))
        self.assertAlmostEqual(self.app.preview_scale, scale)
        self.app.preview_wheel(SimpleNamespace(delta=0, state=4))
        self.assertAlmostEqual(self.app.preview_scale, scale)
        self.app.preview_wheel(SimpleNamespace(delta=-120, state=0))
        self.assertGreater(self.app.canvas.yview()[0], 0)
        self.assertAlmostEqual(self.app.preview_scale, scale)
        for percent, delta, expected in (("500%", 120, 5.0), ("10%", -120, 0.1)):
            self.app.zoom_value.set(percent)
            self.app.set_preview_percent()
            self.app.preview_wheel(SimpleNamespace(delta=delta, state=4))
            self.assertAlmostEqual(self.app.preview_scale, expected)
        with patch.object(self.app, "busy", return_value=True):
            self.app.preview_wheel(SimpleNamespace(delta=120, state=4))
            self.assertAlmostEqual(self.app.preview_scale, 0.1)
        self.app.select_tool("extract")
        self.pump()
        grid = self.app.active_thumbnail_view()
        width = grid.tile_width.get()
        self.app.preview_wheel(SimpleNamespace(delta=120, state=4))
        self.assertEqual(grid.tile_width.get(), width)
        self.assertIs(self.app.active_thumbnail_view(), grid)

    def test_control_drag_does_not_zoom_or_edit_and_grid_selection_is_preserved(self):
        self.app.select_tool("redact")
        self.pump()
        start = SimpleNamespace(x=100, y=180, state=4)
        end = SimpleNamespace(x=100, y=100, state=4)
        scale = self.app.preview_scale
        self.app.draw_start(start)
        self.app.draw_move(end)
        self.app.draw_end(end)
        self.assertEqual(self.app.preview_scale, scale)
        self.assertEqual(self.app.regions, {})
        self.assertIsNone(self.app.drag_start)
        self.app.select_tool("extract")
        self.pump()
        view = self.app.active_thumbnail_view()
        width = view.tile_width.get()
        self.app.zoom_preview(0.25)
        self.assertEqual(view.tile_width.get(), width)
        click = SimpleNamespace(x=100, y=100, state=4)
        selected = set(view.model.selected)
        uid = view.model.items[view.hit(click.x, click.y)][0]
        view.press(click)
        view.release(click)
        self.assertEqual(view.model.selected, selected ^ {uid})

    def test_crop_input_padding_focuses_and_edits_page_and_margin_fields(self):
        self.app.select_tool("crop")
        self.root.update()
        self.root.focus_force()
        self.app.options["crop_scope"].set("지정 페이지")
        self.root.update()
        for key, value in (("pages", "2"), ("margin_left", "8.5")):
            with self.subTest(key=key):
                self.app.canvas.focus_set()
                field = self.app.option_widgets[key]
                field._canvas.event_generate("<ButtonPress-1>", x=3, y=18)
                field._canvas.event_generate("<ButtonRelease-1>", x=3, y=18)
                self.root.update()
                self.assertIs(self.root.focus_get(), field._entry)
                field.delete(0, "end")
                for char in value:
                    field._entry.event_generate(
                        "<KeyPress>", keysym="period" if char == "." else char
                    )
                self.root.update()
                self.assertEqual(self.app.options[key].get(), value)
                field._canvas.event_generate("<ButtonPress-1>", x=field.winfo_width() - 3, y=18)
                field._canvas.event_generate("<ButtonRelease-1>", x=field.winfo_width() - 3, y=18)
                self.root.update()
                self.assertEqual(field._entry.index("insert"), len(value))
        field.configure(state="disabled")
        self.app.canvas.focus_set()
        field._canvas.event_generate("<ButtonPress-1>", x=3, y=18)
        self.root.update()
        self.assertIsNot(self.root.focus_get(), field._entry)

    def test_packaged_navigation_check_matches_single_document_view(self):
        from offline_pdf.diagnostics import verify_ui_navigation

        self.app.show_home()
        verify_ui_navigation(self.app, self.files[0])
        self.assertEqual(self.app.screen, "home")
        self.assertTrue(self.app.home.winfo_ismapped())

    def test_organizer_settings_precede_the_same_common_toolbar(self):
        self.app.select_tool("extract")
        self.root.update()
        header = self.app.organizer.header
        toolbar = self.app.preview_zoom_row
        self.assertIs(header.master, self.app.columns)
        self.assertEqual(toolbar.master, self.app.document_host)
        self.assertLessEqual(header.winfo_rooty() + header.winfo_height(), toolbar.winfo_rooty())
        self.assertTrue(self.app.organizer.winfo_ismapped())
        self.app.organizer.model.selected = {self.app.organizer.model.items[0][0]}
        self.app.organizer.enlarge()
        self.root.update()
        self.assertTrue(header.winfo_ismapped())
        self.assertTrue(toolbar.winfo_ismapped())
        self.app.home_button.invoke()
        self.root.update()
        self.assertTrue(self.app.organizer.winfo_ismapped())

    def test_folded_settings_keep_values_and_percentage_matches_worker_options(self):
        self.app.select_tool("nup")
        self.root.update()
        self.assertFalse(self.app.option_widgets["nup_margin"].winfo_ismapped())
        self.app.toggle_advanced()
        self.root.update()
        self.assertTrue(self.app.option_widgets["nup_margin"].winfo_ismapped())
        self.app.options["nup_margin"].set("7")
        self.app.toggle_advanced()
        self.root.update()
        self.assertFalse(self.app.option_widgets["nup_margin"].winfo_ismapped())
        self.assertEqual(self.app.options["nup_margin"].get(), "7")
        count = self.app.option_widgets["nup_count"]
        self.assertIsInstance(count, ChoicePopup)
        count.invoke()
        self.root.update()
        count.choose("6")
        self.assertEqual(self.app.options["nup_count"].get(), "6")
        self.app.options["nup_count"].set("12")
        self.assertIn("12", count.source_text)
        self.app.select_tool("watermark")
        opacity = self.app.option_widgets["opacity"]
        self.assertEqual(opacity.label.cget("text"), "25%")
        opacity.slider._command(65)
        self.assertEqual(self.app.options["opacity"].get(), "0.65")
        self.app.options["insert_mode"].set("이미지")
        self.assertEqual(opacity.label.cget("text"), "100%")
        self.app.options["opacity"].set("0")
        self.assertEqual(opacity.percent.get(), 0)

    def test_split_entry_opens_unified_workspace_and_saves_selected_file(self):
        self.app.select_tool("split")
        self.assertEqual(self.app.tool, "extract")
        self.assertEqual(self.app.active_job_files(), [self.files[0]])
        self.assertNotIn("split", self.app.cards)
        self.app.organizer.model.set_cuts({2, 4})
        self.app.organizer.draw()
        self.assertIn("PDF 3개로 나눠 저장", self.app.run_button.source_text)
        self.assertEqual([len(group) for group in self.app.organizer.model.segments()], [2, 2, 1])

    def test_drag_reorders_files_preserves_selection_and_blocks_busy(self):
        self.app.select_tool("merge")
        self.root.update()
        listing = self.app.file_list
        listing.click(SimpleNamespace(y=15, state=0))
        listing.drag_file(SimpleNamespace(y=180))
        listing.drop_file(SimpleNamespace(x=20, y=180))
        self.assertEqual(self.app.files, [self.files[1], self.files[2], self.files[0]])
        self.assertEqual(self.app.selected_file(), self.files[0])
        listing.motion_rows = []
        listing.click(SimpleNamespace(y=15, state=4))
        listing.drag_file(SimpleNamespace(y=100))
        listing.drop_file(SimpleNamespace(x=20, y=100))
        self.assertEqual(self.app.files, [self.files[1], self.files[2], self.files[0]])
        listing.drag_origin = (self.files[0], 15)
        listing.drag_target = 0
        self.app.pending_results = {"files": []}
        listing.drop_file(SimpleNamespace(x=20, y=15))
        self.assertEqual(self.app.files[-1], self.files[0])
        self.app.pending_results = None

    def test_drop_registration_visits_segmented_controls_and_unregisters_on_destroy(self):
        self.app.select_tool("protect")
        control = self.app.option_widgets["password_mode"]
        handle = control.winfo_id()
        handles = set()
        support = NativeFileDrop.__new__(NativeFileDrop)
        support.root = self.root
        support._closing = False
        support._poll_count = 11
        support._pending = deque()
        support.ole = SimpleNamespace(
            handles=handles,
            register=handles.add,
            unregister=handles.discard,
        )
        try:
            support._poll_files()
            self.assertIn(handle, handles)
            for child in control.winfo_children():
                self.assertIn(child.winfo_id(), handles)
            self.app.select_tool("merge")
            self.root.update()
            self.assertNotIn(handle, handles)
        finally:
            support._closing = True
            self.root.after_cancel(support._timer_id)
