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
        self.assertTrue(self.app.preview_panel.winfo_ismapped())
        self.assertTrue(
            all(button.cget("state") == "disabled" for button in self.app.preview_controls)
        )
        self.app.add_paths([self.files[0]])
        self.pump()
        self.assertTrue(self.app.preview_panel.winfo_ismapped())
        self.assertTrue(
            any(self.app.canvas.type(item) == "image" for item in self.app.canvas.find_all())
        )
        self.assertIsNotNone(self.app.preview_rect)
        self.assertTrue(
            all(button.cget("state") == "normal" for button in self.app.preview_controls)
        )
        self.app.preview_controls[0].invoke()  # Next, without pressing large preview first.
        self.root.update()
        self.assertTrue(self.app.preview_panel.winfo_ismapped())
        self.assertEqual(self.app.page_index, 1)
        self.assertEqual(self.app.page_label.cget("text"), "2 / 5쪽")
        self.app.add_paths([self.files[1]])
        self.root.update()
        self.assertTrue(self.app.preview_panel.winfo_ismapped())
        self.assertEqual(self.app.screen, "work")

    def test_toolbar_available_in_every_tool_and_fit_controls_work_in_single_view(self):
        for tool in TOOLS:
            with self.subTest(tool=tool):
                self.app.select_tool(tool)
                self.root.update()
                self.assertTrue(self.app.preview_zoom_row.winfo_ismapped())
                self.assertTrue(self.app.preview_nav.winfo_ismapped())
        self.app.select_tool("number")
        self.root.update()
        self.assertTrue(self.app.preview_panel.winfo_ismapped())
        self.app.set_preview_mode("page")
        self.root.update()
        self.assertTrue(self.app.preview_panel.winfo_ismapped())
        self.assertEqual(self.app.preview_mode, "page")
        self.assertEqual(self.app.screen, "work")
        self.assertFalse(hasattr(self.app, "preview_button"))
        self.app.zoom_preview(0.25)
        self.assertEqual(self.app.preview_zoom, 1.25)
        self.assertTrue(self.app.preview_panel.winfo_manager())

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

    def test_split_cut_updates_count_scope_and_ignores_last_page(self):
        self.app.select_tool("split")
        self.assertEqual(self.app.active_job_files(), self.files)
        self.assertIn("전체 3개", self.app.run_button.source_text)
        self.app.page_index = 1
        self.app.add_split_cut()
        self.assertEqual(self.app.options["split_starts"].get(), "3")
        self.assertEqual(self.app.options["split_count"].get(), "2")
        self.assertEqual(self.app.active_job_files(), [self.files[0]])
        self.assertIn("선택 파일", self.app.run_button.source_text)
        self.app.page_index = 1
        self.app.add_split_cut()
        self.assertEqual(self.app.options["split_starts"].get(), "3")
        self.app.page_index = 3
        self.app.add_split_cut()
        self.assertEqual(self.app.options["split_starts"].get(), "3,5")
        self.assertEqual(self.app.options["split_count"].get(), "3")
        self.app.page_index = 4
        self.app.add_split_cut()
        self.assertEqual(self.app.options["split_starts"].get(), "3,5")
        self.app.options["split_mode"].set("페이지별로 나누기")
        self.assertEqual(self.app.active_job_files(), self.files)
        self.assertIn("전체 3개", self.app.run_button.source_text)

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
