"""User flows for compact pickers, live options, split scope and file order."""

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace

import customtkinter as ctk
import pymupdf as pdf

from offline_pdf.app import App
from offline_pdf.compact_controls import ChoicePopup
from offline_pdf.localization import apply_language
from offline_pdf.overlays import POSITIONS


class CompactOptionsTests(unittest.TestCase):
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
            self.files.append(str(path))
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
        self.assertEqual(self.app.screen, "work")
        self.app.home_button.invoke()
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
