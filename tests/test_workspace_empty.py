"""Sidebar empty state stays centred after scrolling and disappears on import."""

import tkinter as tk
import unittest
from types import SimpleNamespace

from offline_pdf.workspace import FileList


class EmptySidebarTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("Desktop unavailable")
        self.root.geometry("240x500")
        self.widget = FileList(self.root, SimpleNamespace(busy=lambda: False))
        self.widget.pack(fill="both", expand=True)
        self.root.update()

    def tearDown(self):
        if hasattr(self, "widget"):
            self.widget.close()
            self.root.destroy()

    def test_hint_visibility_and_centre_after_scrolling_and_resize(self):
        self.widget.draw()
        self.assertEqual(len(self.widget.find_withtag("empty_hint")), 1)
        hint = self.widget.itemcget("empty_hint", "text")
        for extension in ("PDF", "JPG/JPEG", "PNG", "BMP", "GIF", "TIF/TIFF", "WebP"):
            self.assertIn(extension, hint)
        self.widget.set_files([f"file{i}.pdf" for i in range(30)], lambda p: "1쪽")
        self.assertFalse(self.widget.find_withtag("empty_hint"))
        self.widget.yview_moveto(1)
        self.widget.set_files([], lambda p: "")
        self.root.geometry("280x620")
        self.root.update()
        self.assertEqual(self.widget.yview(), (0.0, 1.0))
        x, y = self.widget.coords("empty_hint")
        self.assertAlmostEqual(x, self.widget.winfo_width() / 2, delta=1)
        self.assertAlmostEqual(y, self.widget.winfo_height() / 2, delta=1)
        self.widget.set_files(["new.pdf"], lambda p: "1쪽")
        self.assertFalse(self.widget.find_withtag("empty_hint"))
