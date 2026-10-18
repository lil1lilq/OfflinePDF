import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf as pdf

from offline_pdf.engine import UserError, execute, split_ranges
from offline_pdf.ocr import OCRSetupError, model_directory


class SplitOCRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "열 쪽 문서.pdf"
        with pdf.open() as doc:
            for i in range(10):
                doc.new_page().insert_text((50, 80), f"PAGE {i + 1}")
            doc.save(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def split(self, count, starts, **options):
        return execute(
            {
                "tool": "split",
                "files": [str(self.source)],
                "output": str(self.root),
                "options": dict(
                    split_mode="N개 파일로 나누기",
                    split_count=count,
                    split_starts=starts,
                    **options,
                ),
            }
        )

    def test_boundary_is_start_of_next_file(self):
        folder = self.split(2, "5")
        with (
            pdf.open(sorted(folder.glob("*.pdf"))[0]) as first,
            pdf.open(sorted(folder.glob("*.pdf"))[1]) as second,
        ):
            self.assertEqual(len(first), 4)
            self.assertIn("PAGE 4", first[-1].get_text())
            self.assertEqual(len(second), 6)
            self.assertIn("PAGE 5", second[0].get_text())
        folder = self.split(3, "5,8", pages="invalid ignored in N mode")
        contents = []
        for path in sorted(folder.glob("*.pdf")):
            with pdf.open(path) as doc:
                contents.append([p.get_text().strip() for p in doc])
        self.assertEqual(
            contents,
            [
                ["PAGE " + str(i) for i in range(1, 5)],
                ["PAGE " + str(i) for i in range(5, 8)],
                ["PAGE " + str(i) for i in range(8, 11)],
            ],
        )

    def test_invalid_boundaries_roll_back_and_encryption_is_kept(self):
        for count, starts in [
            (1, ""),
            (11, "2"),
            (3, "5"),
            (3, "5,5"),
            (3, "8,5"),
            (2, "1"),
            (2, "11"),
            (2, "a"),
        ]:
            with self.subTest(count=count, starts=starts), self.assertRaises(UserError):
                self.split(count, starts)
        self.assertFalse(list(self.root.glob("PDF결과_*")))
        with pdf.open(self.source) as doc:
            doc.save(
                self.root / "locked.pdf",
                encryption=pdf.PDF_ENCRYPT_AES_256,
                user_pw="secret",
                owner_pw="secret",
            )
        self.source = self.root / "locked.pdf"
        folder = self.split(2, "5", input_password="secret")
        for path in folder.glob("*.pdf"):
            with pdf.open(path) as doc:
                self.assertTrue(doc.needs_pass)
                self.assertTrue(doc.authenticate("secret"))

    def test_count_equals_page_count(self):
        self.assertEqual(split_ranges(3, 3, "2,3"), [(0, 0), (1, 1), (2, 2)])

    def test_unicode_model_path_fallback_copies_only_models_and_cleans(self):
        models = self.root / "한글 언어자료"
        models.mkdir()
        bundled = Path(__file__).resolve().parents[1] / "tessdata"
        shutil.copyfile(bundled / "eng.traineddata", models / "eng.traineddata")
        (models / "private.pdf").write_bytes(b"NEVER COPY")
        with (
            patch("offline_pdf.ocr.short_path", return_value=None),
            patch("offline_pdf.ocr.cache_roots", return_value=iter([str(self.root)])),
        ):
            with model_directory(models, "eng", windows=True) as path:
                prepared = Path(path)
                self.assertTrue(str(path).isascii())
                self.assertEqual([p.name for p in prepared.iterdir()], ["eng.traineddata"])
                with pdf.open() as doc:
                    page = doc.new_page()
                    page.insert_text((50, 100), "OFFLINE OCR TEST", fontsize=24)
                    data = page.get_pixmap(dpi=150).pdfocr_tobytes(language="eng", tessdata=path)
                with pdf.open("pdf", data) as result:
                    self.assertIn("OFFLINE", result[0].get_text())
            self.assertFalse(prepared.exists())
        self.assertTrue((models / "private.pdf").exists())

    def test_model_cleanup_after_failure_and_missing_language(self):
        models = self.root / "한글 자료"
        models.mkdir()
        (models / "eng.traineddata").write_bytes(b"test")
        with (
            patch("offline_pdf.ocr.short_path", return_value=None),
            patch("offline_pdf.ocr.cache_roots", return_value=iter([str(self.root)])),
        ):
            with self.assertRaisesRegex(RuntimeError, "test"):
                with model_directory(models, "eng", windows=True) as path:
                    prepared = Path(path)
                    raise RuntimeError("test")
            self.assertFalse(prepared.exists())
        with self.assertRaises(OCRSetupError):
            with model_directory(models, "kor"):
                pass


if __name__ == "__main__":
    unittest.main()
