import os
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

import pymupdf as pdf
from offline_pdf.app import App, TOOLS


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:cls.root=tk.Tk()
        except tk.TclError:raise unittest.SkipTest('GUI requires an available Windows desktop or X display.')
        cls.app=App(cls.root);cls.root.update()
        cls.temp=tempfile.TemporaryDirectory();cls.folder=Path(cls.temp.name)
        cls.source=cls.folder/'한글 파일.pdf'
        with pdf.open() as doc:
            for text in ('FIRST','SECOND'):
                p=doc.new_page();p.insert_text((72,72),text)
            doc.save(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.app.close();cls.temp.cleanup()

    def test_a_all_tool_forms_open(self):
        for tool in TOOLS:
            self.app.tool=tool;self.app.configure_form();self.root.update()
            self.assertIn('input_password',self.app.options)
            self.assertEqual(self.app.title.cget('text'),TOOLS[tool][0])

    def test_b_preview_and_page_navigation(self):
        self.app.tool='rotate';self.app.configure_form();self.app.files=[str(self.source)];self.app.sync_list()
        self.app.refresh_preview(reset=True);self.root.update()
        self.assertIsNotNone(self.app.preview_rect);self.assertEqual(self.app.page_index,0)
        self.app.turn(1);self.assertEqual(self.app.page_index,1)
        self.app.turn(1);self.assertEqual(self.app.page_index,1)

    def test_c_complete_gui_job(self):
        self.app.tool='rotate';self.app.configure_form();self.app.files=[str(self.source)];self.app.sync_list()
        self.app.options['pages'].set('1');self.app.options['angle'].set('90');self.app.output.set(str(self.folder))
        with patch('offline_pdf.app.messagebox.showerror',side_effect=AssertionError('Unexpected UI error')):
            self.app.run();deadline=time.monotonic()+20
            while self.app.process is not None and time.monotonic()<deadline:
                self.root.update();time.sleep(.02)
        self.assertIsNone(self.app.process);self.assertIsNotNone(self.app.result_folder)
        with pdf.open(next(Path(self.app.result_folder).glob('*.pdf'))) as doc:
            self.assertEqual(doc[0].rotation,90);self.assertEqual(doc[1].rotation,0)


if __name__=='__main__':unittest.main()
