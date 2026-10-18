"""Transactional image import for every PDF tool, including failure rollback."""

import hashlib
import tempfile
import unittest
from pathlib import Path

import pymupdf as pdf
from PIL import Image

from offline_pdf.engine import Cancelled, UserError, execute


class MixedInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "한글"
        self.root.mkdir()
        self.pdf = self.root / "문서.pdf"
        with pdf.open() as doc:
            doc.new_page(width=100, height=100).insert_text((10, 25), "ORIGINAL", fontsize=8)
            doc.save(self.pdf)
        self.image = self.root / "사진.png"
        with Image.new("RGB", (60, 40), "red") as image:
            image.save(self.image)
        self.frames = self.root / "여러장.tiff"
        with (
            Image.new("RGB", (50, 30), "blue") as first,
            Image.new("RGB", (50, 30), "green") as second,
        ):
            first.save(self.frames, save_all=True, append_images=[second])
        self.originals = {
            p: hashlib.sha256(p.read_bytes()).digest() for p in [self.pdf, self.image, self.frames]
        }

    def tearDown(self):
        for path, digest in self.originals.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), digest)
        self.temp.cleanup()

    def run_tool(self, tool, files, **options):
        events = []
        folder = execute(
            {
                "tool": tool,
                "files": [str(p) for p in files],
                "output": str(self.root),
                "options": options,
            },
            events.append,
        )
        return folder, events

    def test_mixed_order_frames_and_published_input_files(self):
        folder, events = self.run_tool("merge", [self.image, self.pdf, self.frames])
        with pdf.open(next(folder.glob("*.pdf"))) as doc:
            self.assertEqual(len(doc), 4)
            self.assertIn("ORIGINAL", doc[1].get_text())
            self.assertEqual(doc[0].rect, pdf.Rect(0, 0, 60, 40))
        mapping = next(e["files"] for e in events if e["type"] == "converted")
        self.assertEqual(set(mapping), {str(self.image), str(self.frames)})
        for path in mapping.values():
            self.assertTrue(Path(path).is_file())
            self.assertTrue(Path(path).is_relative_to(folder / "입력PDF"))

    def test_rotate_and_split_operate_on_converted_image_frames(self):
        folder, _ = self.run_tool("rotate", [self.frames], angle="90")
        with pdf.open(next(folder.glob("*.pdf"))) as doc:
            self.assertEqual([p.rotation for p in doc], [90, 90])
        folder, _ = self.run_tool(
            "split",
            [self.frames],
            split_mode="N개 파일로 나누기",
            split_count="2",
            split_starts="2",
        )
        self.assertEqual(len(list(folder.glob("*.pdf"))), 2)

    def test_organizer_and_redaction_share_image_preview_coordinates(self):
        folder, _ = self.run_tool("extract", [self.frames], page_plan=[{"page": 1, "rotation": 90}])
        with pdf.open(next(folder.glob("*.pdf"))) as doc:
            self.assertEqual(len(doc), 1)
            self.assertEqual(doc[0].rotation, 90)
        folder, _ = self.run_tool("redact", [self.image], regions={"0": [[0, 0, 30, 40]]})
        with pdf.open(next(folder.glob("*.pdf"))) as doc:
            pix = doc[0].get_pixmap()
            self.assertEqual(pix.pixel(10, 10), (0, 0, 0))
            self.assertGreater(pix.pixel(45, 10)[0], 200)

    def test_images_pdf_accepts_pdf_and_a4_images(self):
        folder, _ = self.run_tool("images_pdf", [self.pdf, self.image], orientation="가로")
        with pdf.open(next(folder.glob("*.pdf"))) as doc:
            self.assertEqual(len(doc), 2)
            self.assertEqual(doc[1].rect, pdf.Rect(0, 0, 842, 595))

    def test_failed_or_cancelled_operations_publish_no_converted_inputs(self):
        for tool, options in [("rotate", {"angle": "135"}), ("delete", {"pages": "1"})]:
            events = []
            with self.assertRaises(UserError):
                execute(
                    {
                        "tool": tool,
                        "files": [str(self.image)],
                        "output": str(self.root),
                        "options": options,
                    },
                    events.append,
                )
            self.assertFalse(any(e["type"] == "converted" for e in events))

        class Cancel:
            value = False

            def is_set(self):
                return self.value

        cancel = Cancel()

        def progress(event):
            if event.get("label") == "이미지를 PDF로 자동 변환 중":
                cancel.value = True

        with self.assertRaises(Cancelled):
            execute(
                {"tool": "merge", "files": [str(self.image)], "output": str(self.root)},
                progress,
                cancel,
            )
        self.assertFalse(list(self.root.glob("PDF결과_*")))
        self.assertFalse(list(self.root.glob(".offline-pdf-*")))

    def test_comparison_does_not_publish_temporary_input_replacements(self):
        folder, events = self.run_tool("upscale", [self.image], preview_only=True, scale="2")
        self.assertTrue((folder / "after.png").is_file())
        self.assertFalse(any(e["type"] == "converted" for e in events))
