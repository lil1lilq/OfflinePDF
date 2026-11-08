"""Real PDF operations through quick-run defaults and the compact task window."""

import queue
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pymupdf as pdf

from offline_pdf.engine import UserError, execute
from offline_pdf.quick import QuickWindow, make_job


class QuickEngineTests(unittest.TestCase):
    def test_defaults_and_password_roundtrip_preserve_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = []
            for name in ("b.pdf", "a.pdf"):
                path = root / name
                with pdf.open() as doc:
                    doc.new_page().insert_text((50, 50), name)
                    doc.new_page()
                    doc.save(path)
                inputs.append(str(path))
            originals = [Path(p).read_bytes() for p in inputs]
            merged = execute(make_job("merge", inputs, root, {}))
            with pdf.open(next(merged.glob("*.pdf"))) as doc:
                self.assertEqual(len(doc), 4)
                self.assertIn("a.pdf", doc[0].get_text())
            split = execute(make_job("split", inputs, root, {}))
            self.assertEqual(len(list(split.glob("*.pdf"))), 4)
            compressed = execute(make_job("compress", inputs, root, {}))
            self.assertEqual(len(list(compressed.glob("*.pdf"))), 2)
            locked = execute(make_job("protect", inputs, root, {}, "secret"))
            paths = [str(p) for p in locked.glob("*.pdf")]
            unlocked = execute(make_job("unlock", paths, root, dict.fromkeys(paths, "secret")))
            with pdf.open(next(unlocked.glob("*.pdf"))) as doc:
                self.assertFalse(doc.needs_pass)
            self.assertEqual(originals, [Path(p).read_bytes() for p in inputs])
            with self.assertRaises(UserError):
                make_job("merge", inputs, root, dict(zip(inputs, ("one", "two"))))
            with self.assertRaises(UserError):
                make_job("merge", [str(root / "missing.pdf")], root, {})


class QuickGuiTests(unittest.TestCase):
    def setUp(self):
        import customtkinter as ctk

        try:
            self.root = ctk.CTk()
        except Exception as exc:
            self.skipTest(f"Desktop unavailable: {type(exc).__name__}")
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.source = self.folder / "quick.pdf"
        with pdf.open() as doc:
            doc.new_page().insert_text((50, 50), "QUICK TEST")
            doc.save(self.source)
        self.inbox = SimpleNamespace(messages=queue.Queue(), close=Mock())
        self.app = QuickWindow(self.root, self.inbox)

    def tearDown(self):
        if hasattr(self, "temp"):
            if self.app.process:
                self.app.cancel_job()
                self.app.finish("cancelled")
            for timer in self.root.tk.call("after", "info"):
                self.root.after_cancel(timer)
            self.root.destroy()
            self.temp.cleanup()

    def wait(self):
        deadline = time.monotonic() + 20
        while self.app.process and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.02)
        self.assertIsNone(self.app.process)
        self.assertEqual(self.app.state, "done", self.app.detail.cget("text"))

    def test_auto_run_password_confirmation_and_results(self):
        self.app.begin("merge", [str(self.source)])
        self.wait()
        self.assertEqual(len(list(Path(self.app.folder).glob("*.pdf"))), 1)
        self.app.begin("protect", [str(self.source)])
        self.assertEqual(self.app.state, "password")
        _, first, second = self.app.prompt
        first.insert(0, "secret")
        second.insert(0, "different")
        self.app.confirm_secret()
        self.assertEqual(self.app.state, "password")
        second.delete(0, "end")
        second.insert(0, "secret")
        self.app.confirm_secret()
        self.wait()
        locked = str(next(Path(self.app.folder).glob("*.pdf")))
        self.app.begin("unlock", [locked])
        self.assertEqual(self.app.state, "password")
        self.app.prompt[1].insert(0, "secret")
        self.app.confirm_secret()
        self.wait()
        self.assertEqual(self.app.passwords, {})
        self.assertEqual(self.app.output_password, "")

    def test_cancel_cleans_staged_results_and_password_fields(self):
        self.app.begin("protect", [str(self.source)])
        self.app.prompt[1].insert(0, "secret")
        self.app.request_close()
        self.assertEqual(self.app.state, "cancelled")
        self.assertEqual(self.app.fields.winfo_children(), [])
        self.app.begin("merge", [str(self.source)])
        self.app.cancel_job()
        self.app.finish("cancelled")
        self.assertFalse(list(self.folder.glob(".offline-pdf-*")))
