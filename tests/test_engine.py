import hashlib
import multiprocessing as mp
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf as pdf

from offline_pdf.engine import (
    Cancelled,
    UserError,
    check_local_path,
    disable_network,
    execute,
    pages,
    worker,
)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "한글 문서.pdf"
        with pdf.open() as doc:
            for text in ["FIRST SECRET", "SECOND PAGE", "THIRD PAGE"]:
                page = doc.new_page()
                page.insert_text((72, 72), text)
            doc.set_metadata({"author": "SENSITIVE AUTHOR"})
            doc.save(self.source)
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def tearDown(self):
        self.assertEqual(self.digest, hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.temp.cleanup()

    def run_tool(self, tool, files=None, **options):
        return execute(
            {
                "tool": tool,
                "files": files or [str(self.source)],
                "output": str(self.root),
                "options": options,
            }
        )

    def output_pdf(self, folder):
        return next(folder.glob("*.pdf"))

    def test_page_parser(self):
        self.assertEqual(pages("3-1,2", 3), [2, 1, 0])
        self.assertEqual(pages("3,1,1", 3, duplicates=True), [2, 0, 0])
        for value in ["0", "4", "1-x", "1,,2"]:
            with self.assertRaises(UserError):
                pages(value, 3)

    def test_merge(self):
        folder = self.run_tool("merge", [str(self.source), str(self.source)])
        with pdf.open(self.output_pdf(folder)) as doc:
            self.assertEqual(len(doc), 6)

    def test_merge_custom_name_and_invalid_paths(self):
        folder = self.run_tool("merge", output_name="합친 문서")
        self.assertTrue((folder / "합친 문서.pdf").is_file())
        for name in (
            "../escape.pdf",
            "sub/escape.pdf",
            "C:\\escape.pdf",
            "CON.pdf",
            "a?.pdf",
            "...pdf",
        ):
            with self.assertRaises(UserError):
                self.run_tool("merge", output_name=name)
            self.assertFalse(list(self.root.glob(".offline-pdf-*")))

    def test_extract_order_duplicates(self):
        folder = self.run_tool("extract", pages="3,1,1")
        with pdf.open(self.output_pdf(folder)) as doc:
            self.assertEqual(len(doc), 3)
            self.assertIn("THIRD", doc[0].get_text())
            self.assertIn("FIRST", doc[2].get_text())

    def test_visual_plan_preserves_order_and_independent_rotation(self):
        plan = [
            {"page": 2, "rotation": 0},
            {"page": 0, "rotation": 90},
            {"page": 0, "rotation": 180},
        ]
        with pdf.open(self.output_pdf(self.run_tool("extract", page_plan=plan))) as doc:
            self.assertEqual([p.rotation for p in doc], [0, 90, 180])
            self.assertEqual(
                [p.get_text().strip() for p in doc], ["THIRD PAGE", "FIRST SECRET", "FIRST SECRET"]
            )
            self.assertEqual(doc.metadata["author"], "SENSITIVE AUTHOR")

    def test_visual_plan_invalid_values_discard_entire_output(self):
        for plan in (
            [],
            [{"page": -1, "rotation": 0}],
            [{"page": 3, "rotation": 0}],
            [{"page": 0, "rotation": 45}],
            [{"page": True, "rotation": 0}],
            {"page": 0},
        ):
            with self.assertRaises(UserError):
                self.run_tool("extract", page_plan=plan)
            self.assertFalse(list(self.root.glob(".offline-pdf-*")))

    def test_visual_plan_keeps_pdf_encrypted(self):
        source = self.output_pdf(self.run_tool("protect", output_password="secret"))
        folder = self.run_tool(
            "extract",
            [str(source)],
            input_password="secret",
            page_plan=[{"page": 1, "rotation": 270}],
        )
        with pdf.open(self.output_pdf(folder)) as doc:
            self.assertTrue(doc.needs_pass)
            self.assertTrue(doc.authenticate("secret"))
            self.assertEqual(doc[0].rotation, 270)
            self.assertIn("SECOND", doc[0].get_text())

    def test_split_and_delete(self):
        self.assertEqual(len(list(self.run_tool("split", pages="1,3").glob("*.pdf"))), 2)
        folder = self.run_tool("delete", pages="1,3")
        with pdf.open(self.output_pdf(folder)) as doc:
            self.assertEqual(len(doc), 1)
            self.assertIn("SECOND", doc[0].get_text())

    def test_no_empty_delete(self):
        with self.assertRaises(UserError):
            self.run_tool("delete")
        self.assertFalse(list(self.root.glob(".offline-pdf-*")))

    def test_rotate(self):
        with pdf.open(self.output_pdf(self.run_tool("rotate", pages="2", angle="90"))) as doc:
            self.assertEqual(doc[1].rotation, 90)
            self.assertEqual(doc[0].rotation, 0)

    def test_password_round_trip(self):
        locked = self.output_pdf(self.run_tool("protect", output_password="비밀123"))
        with pdf.open(locked) as doc:
            self.assertTrue(doc.needs_pass)
            self.assertFalse(doc.authenticate("wrong"))
            self.assertTrue(doc.authenticate("비밀123"))
        with self.assertRaises(UserError):
            self.run_tool("unlock", [str(locked)], input_password="wrong")
        unlocked = self.output_pdf(self.run_tool("unlock", [str(locked)], input_password="비밀123"))
        with pdf.open(unlocked) as doc:
            self.assertFalse(doc.needs_pass)
        transformed = self.output_pdf(
            self.run_tool("rotate", [str(locked)], input_password="비밀123", angle="90")
        )
        with pdf.open(transformed) as doc:
            self.assertTrue(doc.needs_pass)

    def test_images_roundtrip(self):
        folder = self.run_tool("pdf_images", pages="1", dpi="72", format="PNG")
        image = next(folder.glob("*.png"))
        result = self.run_tool("images_pdf", [str(image)])
        with pdf.open(self.output_pdf(result)) as doc:
            self.assertEqual(len(doc), 1)

    def test_text_export(self):
        result = self.run_tool("text", pages="2")
        text = next(result.glob("*.txt")).read_text(encoding="utf-8-sig")
        self.assertIn("SECOND", text)
        self.assertNotIn("SECRET", text)

    def test_watermark_number_stamp_crop_clean_compress(self):
        for tool, options in [
            ("watermark", {"text": "내부 업무용"}),
            ("number", {"start": "10"}),
            ("crop", {"margin": "5"}),
            ("clean", {}),
            ("compress", {}),
        ]:
            folder = self.run_tool(tool, **options)
            with pdf.open(self.output_pdf(folder)) as doc:
                self.assertEqual(len(doc), 3)
                if tool == "number":
                    self.assertIn("10", doc[0].get_text())
                if tool == "clean":
                    self.assertFalse(doc.metadata.get("author"))
                if tool == "crop":
                    self.assertLess(doc[0].rect.width, 595)
        folder = self.run_tool("pdf_images", pages="1", dpi="72", format="PNG")
        self.run_tool("stamp", stamp_path=str(next(folder.glob("*.png"))))

    def test_redaction_removes_text_and_metadata(self):
        with pdf.open(self.source) as doc:
            rect = list(doc[0].search_for("SECRET")[0] + (-1, -1, 1, 1))
        folder = self.run_tool("redact", regions={"0": [rect]})
        with pdf.open(self.output_pdf(folder)) as doc:
            self.assertNotIn("SECRET", "".join(p.get_text() for p in doc))
            self.assertFalse(doc.metadata.get("author"))
            self.assertIn("FIRST", doc[0].get_text())

    def test_redaction_shared_image(self):
        # Same image XObject used on two pages: only selected occurrence is removed.
        source = self.root / "scanned.pdf"
        pix = pdf.Pixmap(pdf.csRGB, pdf.IRect(0, 0, 20, 20), False)
        pix.clear_with(255)
        with pdf.open() as doc:
            p = doc.new_page(width=100, height=100)
            xref = p.insert_image(p.rect, stream=pix.tobytes("png"))
            p = doc.new_page(width=100, height=100)
            p.insert_image(p.rect, xref=xref)
            doc.save(source)
        folder = self.run_tool("redact", [str(source)], regions={"0": [[0, 0, 100, 100]]})
        with pdf.open(self.output_pdf(folder)) as doc:
            red = doc[0].get_pixmap()
            white = doc[1].get_pixmap()
            self.assertEqual(red.pixel(50, 50), (0, 0, 0))
            self.assertEqual(white.pixel(50, 50), (255, 255, 255))

    def test_redaction_refuses_crop(self):
        cropped = self.output_pdf(self.run_tool("crop", margin="5"))
        with self.assertRaises(UserError):
            self.run_tool("redact", [str(cropped)], regions={"0": [[0, 0, 100, 100]]})

    def test_redaction_cleans_attachments_widgets_annotations(self):
        source = self.root / "form.pdf"
        with pdf.open(self.source) as doc:
            page = doc[0]
            page.add_text_annot((200, 200), "SECRET COMMENT")
            w = pdf.Widget()
            w.field_type = pdf.PDF_WIDGET_TYPE_TEXT
            w.field_name = "secret"
            w.field_value = "SECRET FORM"
            w.rect = pdf.Rect(200, 250, 400, 280)
            page.add_widget(w)
            doc.embfile_add("private.txt", b"SECRET ATTACHMENT")
            doc.save(source)
        folder = self.run_tool("redact", [str(source)], regions={"0": [[0, 0, 150, 100]]})
        with pdf.open(self.output_pdf(folder)) as doc:
            self.assertEqual(doc.embfile_count(), 0)
            self.assertFalse(list(doc[0].widgets() or []))
            self.assertFalse(list(doc[0].annots() or []))

    def test_transaction_cleanup(self):
        bad = self.root / "bad.pdf"
        bad.write_bytes(b"not a PDF")
        with self.assertRaises(UserError):
            self.run_tool("compress", [str(self.source), str(bad)])
        self.assertFalse(list(self.root.glob(".offline-pdf-*")))
        self.assertFalse(list(self.root.glob("PDF결과_*")))

    def test_cancel(self):
        event = mp.get_context("spawn").Event()
        event.set()
        with self.assertRaises(Cancelled):
            execute(
                {"tool": "compress", "files": [str(self.source)], "output": str(self.root)},
                cancel=event,
            )
        self.assertFalse(list(self.root.glob(".offline-pdf-*")))

    def test_ocr_requires_local_models(self):
        with self.assertRaises(UserError):
            self.run_tool("ocr", tessdata=str(self.root / "missing"))

    def test_ocr_bundled_models(self):
        source = self.root / "ocr.pdf"
        with pdf.open() as doc:
            page = doc.new_page()
            page.insert_text((50, 100), "OFFLINE PDF TEST 12345", fontsize=28)
            pix = page.get_pixmap(dpi=150, colorspace=pdf.csRGB, alpha=False)
        with pdf.open() as doc:
            page = doc.new_page()
            page.insert_image(page.rect, stream=pix.tobytes("png"))
            doc.save(source)
        models = Path(__file__).resolve().parents[1] / "tessdata"
        folder = self.run_tool("ocr", [str(source)], tessdata=str(models), language="eng")
        with pdf.open(self.output_pdf(folder)) as result:
            self.assertIn("OFFLINE", result[0].get_text())

    def test_local_path_policy(self):
        with self.assertRaises(UserError):
            check_local_path("//server/share/file.pdf")
        cloud = self.root / "cloud"
        cloud.mkdir()
        with patch.dict("os.environ", {"OneDrive": str(cloud)}):
            with self.assertRaises(UserError):
                check_local_path(cloud / "result.pdf")
        with self.assertRaises(UserError):
            check_local_path(self.root / "Dropbox" / "x.pdf")

    def test_network_guard(self):
        import socket

        with (
            patch.object(socket, "socket"),
            patch.object(socket, "create_connection"),
            patch.object(socket, "getaddrinfo"),
        ):
            disable_network()
            with self.assertRaises(PermissionError):
                socket.socket()
            with self.assertRaises(PermissionError):
                socket.create_connection(("example.com", 443))
            with self.assertRaises(PermissionError):
                socket.getaddrinfo("example.com", 443)

    def test_worker_spawn_and_network_policy(self):
        ctx = mp.get_context("spawn")
        q = ctx.Queue()
        event = ctx.Event()
        proc = ctx.Process(
            target=worker,
            args=(
                {"tool": "compress", "files": [str(self.source)], "output": str(self.root)},
                q,
                event,
            ),
        )
        proc.start()
        messages = []
        try:
            while True:
                item = q.get(timeout=25)
                messages.append(item)
                if item["type"] in ("done", "error", "cancelled"):
                    break
            proc.join(timeout=10)
            self.assertEqual(proc.exitcode, 0)
            self.assertEqual(messages[-1]["type"], "done")
        finally:
            if proc.is_alive():
                proc.terminate()
                proc.join()
            q.close()


if __name__ == "__main__":
    unittest.main()
