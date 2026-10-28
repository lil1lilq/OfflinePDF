import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf as pdf

from offline_pdf.app import App


class NupGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("GUI requires a desktop or X display.")
        cls.app = App(cls.root)
        cls.app.auto_open.set(False)
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        cls.source = cls.folder / "모아찍기.pdf"
        with pdf.open() as doc:
            for i in range(10):
                page = doc.new_page()
                page.insert_text((72, 72), f"PAGE_{i + 1}")
            doc.save(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.app.close()
        cls.temp.cleanup()

    def setUp(self):
        self.app.select_tool("nup")
        self.app.files = [str(self.source)]
        self.app.sync_list()
        self.app.refresh_preview(reset=True)
        self.root.update()

    def test_defaults_and_minimum_window_controls(self):
        self.assertEqual(self.app.options["nup_count"].get(), "4")
        self.assertEqual(self.app.options["nup_margin"].get(), "0")
        self.assertEqual(self.app.options["nup_fit"].get(), "전체 내용 유지")
        self.root.geometry("900x620")
        self.root.update()
        self.assertTrue(self.app.run_button.winfo_ismapped())
        for _, cell in self.app.form_cells:
            self.assertTrue(cell.winfo_ismapped())
            self.assertLess(
                cell.winfo_rooty() + cell.winfo_height(), self.app.run_button.winfo_rooty()
            )
        self.root.geometry("1280x800")

    def test_preview_navigation_and_invalid_settings(self):
        self.app.show_preview()
        self.root.update()
        self.app.refresh_preview(reset=True)
        self.assertEqual(self.app.preview_rect, (595, 842))
        self.assertEqual(self.app.page_label.cget("text"), "1 / 3쪽")
        self.app.turn(1)
        self.assertEqual(self.app.page_label.cget("text"), "2 / 3쪽")
        self.app.turn(100)
        self.assertEqual(self.app.page_label.cget("text"), "3 / 3쪽")
        self.app.hide_preview()
        self.app.options["nup_count"].set("3")
        self.app.options["nup_orientation"].set("가로")
        self.app.refresh_preview(reset=True)
        self.assertEqual(self.app.preview_rect, (842, 595))
        self.assertEqual(self.app.page_label.cget("text"), "1 / 4쪽")
        self.app.options["nup_count"].set("bad")
        self.app.refresh_preview()
        self.assertEqual(self.app.page_label.cget("text"), "설정을 확인하세요")
        self.assertIsNone(self.app.preview_rect)

    def test_worker_export_and_result_chaining(self):
        self.app.save_mode.set("지정한 폴더")
        self.app.output.set(str(self.folder))
        self.app.options["nup_count"].set("3")
        with patch("tkinter.messagebox.showerror", side_effect=AssertionError("UI error")):
            self.app.run()
            deadline = time.monotonic() + 20
            while self.app.process is not None and time.monotonic() < deadline:
                self.root.update()
                time.sleep(0.02)
        self.assertIsNone(self.app.process)
        with pdf.open(self.app.result_files[0]) as result:
            self.assertEqual(len(result), 4)
            self.assertIn("PAGE_10", result[-1].get_text())
        self.app.continue_with_result()
        self.app.select_tool("compress")
        self.assertEqual(tuple(self.app.files), self.app.result_files)
