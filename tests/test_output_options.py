import hashlib
import tempfile
import threading
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pymupdf as pdf
from PIL import Image

from offline_pdf.engine import Cancelled, UserError, execute
from offline_pdf.output_options import BLANK_MODE, compression_trials, size_limit


class OutputOptionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "원본.pdf"
        noise = np.random.default_rng(4).integers(0, 256, (800, 800, 3), dtype=np.uint8)
        stream = BytesIO()
        with Image.fromarray(noise) as image:
            image.save(stream, format="PNG")
        with pdf.open() as doc:
            page = doc.new_page(width=288, height=288)
            page.insert_image(page.rect, stream=stream.getvalue())
            page.insert_text((20, 20), "KEEP TEXT")
            doc.new_page()
            doc.set_toc([[1, "Content", 1]])
            doc.save(self.source)
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def tearDown(self):
        self.assertEqual(self.digest, hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertFalse(list(self.root.glob(".offline-pdf-*")))
        self.temp.cleanup()

    def run_job(
        self,
        tool="compress",
        files=None,
        passwords=None,
        emit=lambda e: None,
        cancel=None,
        **options,
    ):
        return execute(
            {
                "tool": tool,
                "files": files or [str(self.source)],
                "output": str(self.root),
                "passwords": passwords or {},
                "options": options,
            },
            emit,
            cancel,
        )

    def test_target_size_and_blank_removal_keep_text_bookmarks(self):
        events = []
        folder = self.run_job(
            compression="목표 용량", target_mb="0.08", remove_blank=BLANK_MODE, emit=events.append
        )
        target = next(folder.glob("*.pdf"))
        self.assertLessEqual(target.stat().st_size, 80000)
        with pdf.open(target) as doc:
            self.assertEqual(len(doc), 1)
            self.assertIn("KEEP TEXT", doc[0].get_text())
            self.assertEqual(doc.get_toc(), [[1, "Content", 1]])
        self.assertFalse((folder / ".output-work").exists())
        self.assertEqual(events[-1]["removed_blank_pages"], 1)
        self.assertTrue(events[-1]["size_checked"])

    def test_already_under_target_does_not_rewrite_images(self):
        with patch.object(
            pdf.Document, "rewrite_images", side_effect=AssertionError("unnecessary")
        ):
            folder = self.run_job(compression="목표 용량", target_mb="10")
        self.assertLessEqual(next(folder.glob("*.pdf")).stat().st_size, 10_000_000)

    def test_ai_limit_uses_post_enhancement_pdf(self):
        # Inference is covered by test_enhancement; isolate size publication here.
        with patch("offline_pdf.enhance.enhance_pdf") as inference:
            folder = self.run_job("upscale", max_output_mb="0.08")
        inference.assert_called_once()
        self.assertLessEqual(next(folder.glob("*.pdf")).stat().st_size, 80000)

    def test_blank_scan_and_faint_pixel_annotation_widget_vector_are_preserved(self):
        source = self.root / "빈페이지기준.pdf"
        with pdf.open() as doc:
            doc.new_page()
            for marked in (False, True):
                with Image.new("RGB", (64, 64), "white") as image:
                    if marked:
                        image.putpixel((32, 32), (254, 255, 255))
                    stream = BytesIO()
                    image.save(stream, format="PNG")
                page = doc.new_page()
                page.insert_image(page.rect, stream=stream.getvalue())
            page = doc.new_page()
            page.add_text_annot((30, 30), "NOTE")
            page = doc.new_page()
            page.draw_line((20, 20), (40, 40), color=(0.99, 0.99, 0.99))
            page = doc.new_page()
            page.insert_text((30, 30), "HIDDEN", render_mode=3)
            page = doc.new_page()
            widget = pdf.Widget()
            widget.field_name = "empty"
            widget.field_type = pdf.PDF_WIDGET_TYPE_TEXT
            widget.rect = pdf.Rect(20, 20, 100, 50)
            page.add_widget(widget)
            page = doc.new_page()
            page.insert_link(
                {
                    "kind": pdf.LINK_URI,
                    "from": pdf.Rect(10, 10, 50, 50),
                    "uri": "https://example.com",
                }
            )
            doc.save(source)
        folder = self.run_job("rotate", files=[str(source)], angle="90", remove_blank=BLANK_MODE)
        with pdf.open(next(folder.glob("*.pdf"))) as doc:
            self.assertEqual(len(doc), 6)
            self.assertTrue(doc[1].first_annot)
            self.assertTrue(doc[2].get_drawings())
            self.assertIn("HIDDEN", doc[3].get_text())
            self.assertTrue(next(doc[4].widgets(), None))
            self.assertTrue(doc[5].get_links())

    def test_blank_option_off_by_default(self):
        folder = self.run_job(compression="무손실")
        with pdf.open(next(folder.glob("*.pdf"))) as doc:
            self.assertEqual(len(doc), 2)

    def test_all_blank_batch_is_not_published(self):
        source = self.root / "전부빈페이지.pdf"
        with pdf.open() as doc:
            doc.new_page()
            doc.save(source)
        with self.assertRaisesRegex(UserError, "모든 결과 페이지"):
            self.run_job(
                files=[str(self.source), str(source)], compression="무손실", remove_blank=BLANK_MODE
            )
        self.assertFalse(list(self.root.glob("PDF결과_*")))

    def test_impossible_limit_rolls_back_batch(self):
        source = self.root / "용량초과.pdf"
        with pdf.open() as doc:
            page = doc.new_page()
            page.insert_text((20, 20), "KEEP")
            doc.set_metadata({"subject": "X" * 20000})
            doc.save(source)
        with self.assertRaisesRegex(UserError, "시도한 최소 용량"):
            self.run_job(
                files=[str(self.source), str(source)],
                compression="목표 용량",
                target_mb="0.01",
                min_dpi="300",
                min_quality="95",
            )
        self.assertFalse(list(self.root.glob("PDF결과_*")))

    def test_each_output_limit_includes_encryption(self):
        paths = []
        passwords = {}
        for index, password in enumerate(("first", "second")):
            path = self.root / f"잠김{index}.pdf"
            with pdf.open(self.source) as doc:
                doc.save(
                    path, encryption=pdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password
                )
            paths.append(str(path))
            passwords[str(path)] = password
        folder = self.run_job(
            files=paths,
            passwords=passwords,
            compression="목표 용량",
            target_mb="0.08",
            remove_blank=BLANK_MODE,
        )
        for target, password in zip(sorted(folder.glob("*.pdf")), ("first", "second")):
            self.assertLessEqual(target.stat().st_size, 80000)
            with pdf.open(target) as doc:
                self.assertTrue(doc.needs_pass)
                self.assertTrue(doc.authenticate(password))
                self.assertEqual(len(doc), 1)
                self.assertIn("KEEP TEXT", doc[0].get_text())

    def test_merge_arbitrary_filename_and_new_password(self):
        folder = self.run_job(
            "merge", output_name="임의이름.pdf", output_password="new", remove_blank=BLANK_MODE
        )
        with pdf.open(folder / "임의이름.pdf") as doc:
            self.assertTrue(doc.authenticate("new"))
            self.assertEqual(len(doc), 1)

    def test_image_inputs_keep_inputpdf_but_clean_result(self):
        white = self.root / "하양.png"
        with Image.new("RGB", (64, 64), "white") as image:
            image.save(white)
        folder = self.run_job(
            "merge", files=[str(white), str(self.source)], remove_blank=BLANK_MODE
        )
        self.assertEqual(len(list((folder / "입력PDF").glob("*.pdf"))), 1)
        with pdf.open(next(folder.glob("*.pdf"))) as doc:
            self.assertEqual(len(doc), 1)

    def test_cancel_during_size_trial_does_not_publish(self):
        cancel = threading.Event()

        def emit(event):
            if event.get("label", "").startswith("용량 맞추기"):
                cancel.set()

        with self.assertRaises(Cancelled):
            self.run_job(compression="목표 용량", target_mb="0.08", emit=emit, cancel=cancel)
        self.assertFalse(list(self.root.glob("PDF결과_*")))

    def test_invalid_values_rejected_before_processing(self):
        for value in ("", "NaN", "Infinity", "-1", "0", "0.009", "100001", "abc"):
            with self.subTest(value=value), self.assertRaises(UserError):
                self.run_job(compression="목표 용량", target_mb=value)
        for key, value in (
            ("min_dpi", "71"),
            ("min_dpi", "301"),
            ("min_quality", "29"),
            ("min_quality", "96"),
            ("remove_blank", "bad"),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(UserError):
                self.run_job(compression="목표 용량", target_mb="5", **{key: value})
        self.assertEqual(size_limit({"max_output_mb": ""}, "upscale"), None)
        self.assertEqual(size_limit({"max_output_mb": "1.25"}, "upscale"), 1250000)
        self.assertFalse(list(self.root.glob("PDF결과_*")))

    def test_trials_never_go_below_user_floors(self):
        trials = list(compression_trials(110, 62))
        self.assertEqual(trials[-1], (110, 62))
        self.assertTrue(all(dpi >= 110 and quality >= 62 for dpi, quality in trials))


if __name__ == "__main__":
    unittest.main()
