"""Real damaged PDFs, conservative failure, source preservation and import flow."""

import hashlib
import multiprocessing as mp
import re
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import customtkinter as ctk
import pymupdf as pdf

from offline_pdf.engine import Cancelled, UserError
from offline_pdf.repair import (
    ENCRYPTION_FAILED,
    REPAIR_FAILED,
    needs_repair,
    publish_repaired,
    repair_pdf,
    repair_worker,
)
from offline_pdf.repair_dialog import _run_repair, prepare_pdf_import


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.source = self.folder / "손상 문서.pdf"
        self.output = self.folder / "복구.pdf"
        with pdf.open() as doc:
            page = doc.new_page(width=300, height=400)
            page.insert_text((40, 70), "SEARCHABLE TEXT")
            page.add_text_annot((80, 90), "KEEP ANNOTATION")
            page.insert_link(
                {
                    "kind": pdf.LINK_URI,
                    "from": pdf.Rect(40, 40, 80, 60),
                    "uri": "https://example.org",
                }
            )
            page = doc.new_page(width=400, height=300)
            page.insert_text((40, 70), "SECOND PAGE")
            page.set_cropbox(pdf.Rect(10, 10, 390, 290))
            page.set_rotation(90)
            doc.set_metadata({"title": "KEEP TITLE"})
            self.clean = doc.tobytes()
        self.source.write_bytes(re.sub(rb"startxref\s+\d+", b"startxref\n1", self.clean))
        self.original = hashlib.sha256(self.source.read_bytes()).digest()

    def tearDown(self):
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).digest(), self.original)
        self.assertFalse(list(self.folder.glob(".offlinepdf-*")))
        self.temp.cleanup()

    def test_real_xref_recovery_retains_text_geometry_links_annotations(self):
        self.assertTrue(needs_repair(self.source))
        repair_pdf(self.source, self.output)
        self.assertFalse(needs_repair(self.output))
        with pdf.open(self.output) as doc:
            self.assertEqual(doc.page_count, 2)
            self.assertIn("SEARCHABLE TEXT", doc[0].get_text())
            self.assertEqual(next(doc[0].annots()).info["content"], "KEEP ANNOTATION")
            self.assertEqual(doc[0].get_links()[0]["uri"], "https://example.org")
            self.assertEqual(doc[1].rotation, 90)
            self.assertEqual(tuple(doc[1].cropbox), (10, 10, 390, 290))
            self.assertEqual(doc.metadata["title"], "KEEP TITLE")
            self.assertEqual(doc[0].get_images(), [])  # text was not rasterized

    def test_missing_xref_and_trailer_can_be_rebuilt(self):
        broken = self.folder / "missing-xref.pdf"
        broken.write_bytes(self.clean[: self.clean.index(b"xref")] + b"%%EOF\n")
        repair_pdf(broken, self.output)
        with pdf.open(self.output) as doc:
            self.assertEqual(len(doc), 2)
            self.assertIn("SECOND PAGE", doc[1].get_text())

    def test_normal_file_is_not_offered_repair(self):
        clean = self.folder / "normal.pdf"
        clean.write_bytes(self.clean)
        self.assertFalse(needs_repair(clean))
        app = SimpleNamespace(root=Mock())
        with patch("offline_pdf.repair_dialog.messagebox.askyesno") as prompt:
            self.assertEqual(prepare_pdf_import(app, clean), clean)
        prompt.assert_not_called()

    def test_existing_file_and_source_cannot_be_overwritten(self):
        for target in (self.source, self.output):
            if target == self.output:
                target.write_bytes(b"DO NOT OVERWRITE")
            before = target.read_bytes()
            with self.assertRaises(UserError):
                repair_pdf(self.source, target)
            self.assertEqual(target.read_bytes(), before)
        with self.assertRaises(UserError):
            publish_repaired(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), b"DO NOT OVERWRITE")

    def test_incomplete_file_fails_without_output(self):
        broken = self.folder / "truncated.pdf"
        broken.write_bytes(b"%PDF-1.6\nnot a document\n")
        self.assertTrue(needs_repair(broken))
        with self.assertRaisesRegex(UserError, "자동"):
            repair_pdf(broken, self.output)
        self.assertFalse(self.output.exists())

    def test_valid_encryption_uses_password_flow_and_is_not_stripped(self):
        encrypted = self.folder / "encrypted.pdf"
        with pdf.open(stream=self.clean, filetype="pdf") as doc:
            doc.save(
                encrypted, encryption=pdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner"
            )
        self.assertFalse(needs_repair(encrypted))
        with self.assertRaisesRegex(UserError, "암호화된"):
            repair_pdf(encrypted, self.output)
        self.assertFalse(self.output.exists())

    def test_invalid_encryption_key_is_not_guessed_or_trimmed(self):
        encrypted = self.folder / "bad-encryption.pdf"
        with pdf.open(stream=self.clean, filetype="pdf") as doc:
            data = doc.tobytes(encryption=pdf.PDF_ENCRYPT_AES_256, owner_pw="owner")
        data, count = re.subn(
            rb"/OE\s*<([0-9a-fA-F]{64})>", rb"/OE<\g<1>00000000000000000000000000000000>", data
        )
        self.assertEqual(count, 1)
        encrypted.write_bytes(data)
        digest = hashlib.sha256(data).digest()
        with self.assertRaisesRegex(UserError, "암호화 정보"):
            needs_repair(encrypted)
        with self.assertRaises(UserError) as raised:
            repair_pdf(encrypted, self.output)
        self.assertEqual(str(raised.exception), ENCRYPTION_FAILED)
        self.assertEqual(hashlib.sha256(encrypted.read_bytes()).digest(), digest)
        self.assertFalse(self.output.exists())

    def test_signature_document_is_not_rewritten(self):
        signed = self.folder / "signature.pdf"
        with pdf.open(stream=self.clean, filetype="pdf") as doc:
            doc.xref_set_key(doc.pdf_catalog(), "AcroForm", "<< /SigFlags 3 >>")
            doc.save(signed)
        with self.assertRaisesRegex(UserError, "전자서명"):
            repair_pdf(signed, self.output)
        self.assertFalse(self.output.exists())

    def test_cancel_during_validation_cleans_staging(self):
        cancel = mp.get_context("spawn").Event()

        def progress(done, total):
            if done > total // 2:
                cancel.set()

        with self.assertRaises(Cancelled):
            repair_pdf(self.source, self.output, cancel=cancel, progress=progress)
        self.assertFalse(self.output.exists())

    def test_changed_content_is_rejected(self):
        from offline_pdf.repair import _page_signature

        calls = 0

        def changed(page):
            nonlocal calls
            calls += 1
            signature = _page_signature(page)
            return signature if calls <= 2 else ("DIFFERENT",)

        with patch("offline_pdf.repair._page_signature", side_effect=changed):
            with self.assertRaisesRegex(UserError, "내용이 달라"):
                repair_pdf(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_spawned_worker_reports_verified_result(self):
        context = mp.get_context("spawn")
        events, cancel = context.Queue(), context.Event()
        process = context.Process(
            target=repair_worker, args=(str(self.source), str(self.output), events, cancel)
        )
        try:
            process.start()
            self.assertEqual(events.get(timeout=20), ("done", ""))
            process.join(timeout=5)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode, 0)
            self.assertFalse(needs_repair(self.output))
        finally:
            if process.is_alive():
                process.terminate()
                process.join()
            events.close()
            events.join_thread()

    def test_import_decline_failure_and_success(self):
        app = SimpleNamespace(root=Mock())
        with patch("offline_pdf.repair_dialog.messagebox.askyesno", return_value=False):
            self.assertIsNone(prepare_pdf_import(app, self.source))
            self.assertFalse(app._repairing)
        for success in (False, True):

            def recover(parent, source, target):
                if not success:
                    raise UserError(REPAIR_FAILED)
                return repair_pdf(source, target)

            with (
                patch("offline_pdf.repair_dialog.messagebox.askyesno", return_value=True),
                patch(
                    "offline_pdf.repair_dialog.filedialog.asksaveasfilename",
                    return_value=str(self.output),
                ),
                patch("offline_pdf.repair_dialog._run_repair", side_effect=recover),
                patch("offline_pdf.repair_dialog.messagebox.showerror") as error,
                patch("offline_pdf.repair_dialog.messagebox.showinfo"),
            ):
                self.assertEqual(
                    prepare_pdf_import(app, self.source), self.output if success else None
                )
                self.assertEqual(error.call_count, 0 if success else 1)
                self.assertFalse(app._repairing)


class RepairDialogTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = ctk.CTk()
        except tk.TclError:
            self.skipTest("GUI requires a display")
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.source = self.folder / "broken.pdf"
        self.destination = self.folder / "recovered.pdf"
        with pdf.open() as doc:
            doc.new_page().insert_text((50, 70), "PRESERVE TEXT")
            data = doc.tobytes()
        self.source.write_bytes(re.sub(rb"startxref\s+\d+", b"startxref\n1", data))
        self.root.update()

    def tearDown(self):
        if hasattr(self, "root"):
            for timer in self.root.tk.call("after", "info"):
                self.root.after_cancel(timer)
            self.root.destroy()
            self.temp.cleanup()

    def test_real_modal_worker_saves_recovery_without_blocking_events(self):
        ticks = []
        self.root.after(10, lambda: ticks.append("responsive"))
        self.assertEqual(_run_repair(self.root, self.source, self.destination), self.destination)
        self.assertEqual(ticks, ["responsive"])
        self.assertFalse(needs_repair(self.destination))
        self.assertFalse(list(self.folder.glob(".offlinepdf-*")))
        self.assertIsNone(self.root.grab_current())

    def test_cancel_button_stops_worker_and_removes_staging(self):
        def cancel(widget):
            for child in widget.winfo_children():
                if isinstance(child, ctk.CTkButton) and child.cget("text") == "취소":
                    child.invoke()
                    return True
                if cancel(child):
                    return True
            return False

        self.root.after(10, lambda: cancel(self.root))
        self.assertIsNone(_run_repair(self.root, self.source, self.destination))
        self.assertFalse(self.destination.exists())
        self.assertFalse(list(self.folder.glob(".offlinepdf-*")))
        self.assertIsNone(self.root.grab_current())

    def test_staging_creation_failure_releases_modal(self):
        with patch(
            "offline_pdf.repair_dialog.tempfile.TemporaryDirectory", side_effect=PermissionError
        ):
            with self.assertRaises(PermissionError):
                _run_repair(self.root, self.source, self.destination)
        self.assertIsNone(self.root.grab_current())
        self.assertFalse(any(isinstance(w, ctk.CTkToplevel) for w in self.root.winfo_children()))


if __name__ == "__main__":
    unittest.main()
