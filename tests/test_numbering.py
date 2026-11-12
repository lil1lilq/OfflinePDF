import tempfile
import unittest
from pathlib import Path

import pymupdf as pdf

from offline_pdf.engine import UserError, execute
from offline_pdf.numbering import draw_number
from offline_pdf.overlays import POSITIONS


class NumberingTests(unittest.TestCase):
    def test_positions_sizes_and_rotations_remain_visible(self):
        for rotation in (0, 90, 180, 270):
            for position in POSITIONS:
                for size in (8, 11, 24, 72):
                    with (
                        self.subTest(rotation=rotation, position=position, size=size),
                        pdf.open() as doc,
                    ):
                        page = doc.new_page(width=400, height=600)
                        page.set_rotation(rotation)
                        draw_number(
                            page,
                            2,
                            {
                                "start": "10",
                                "number_position": position,
                                "number_font_size": str(size),
                            },
                        )
                        spans = [
                            s
                            for b in page.get_text("dict")["blocks"]
                            for line in b.get("lines", [])
                            for s in line["spans"]
                        ]
                        self.assertEqual(spans[0]["text"], "12")
                        self.assertAlmostEqual(spans[0]["size"], size)
                        rect = pdf.Rect(spans[0]["bbox"]) * page.rotation_matrix
                        self.assertTrue(page.rect.contains(rect), rect)
                        if "위" in position:
                            self.assertLess(rect.y1, page.rect.height / 2)
                        if "아래" in position:
                            self.assertGreater(rect.y0, page.rect.height / 2)
                        if "왼쪽" in position:
                            self.assertLess(rect.x1, page.rect.width / 2)
                        if "오른쪽" in position:
                            self.assertGreater(rect.x0, page.rect.width / 2)

    def test_export_selected_order_and_original_preservation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.pdf"
            with pdf.open() as doc:
                for _ in range(3):
                    doc.new_page()
                doc.save(source)
            original = source.read_bytes()
            result = execute(
                {
                    "tool": "number",
                    "files": [str(source)],
                    "output": temporary,
                    "options": {
                        "pages": "3,1",
                        "start": "10",
                        "number_position": "오른쪽 위",
                        "number_font_size": "24",
                    },
                }
            )
            with pdf.open(next(result.glob("*.pdf"))) as doc:
                self.assertEqual(doc[2].get_text().strip(), "10")
                self.assertEqual(doc[0].get_text().strip(), "11")
                self.assertEqual(doc[1].get_text(), "")
            self.assertEqual(source.read_bytes(), original)

    def test_invalid_options(self):
        for options in (
            {"number_font_size": "nan"},
            {"number_font_size": "0"},
            {"number_font_size": "100"},
            {"number_position": "invalid"},
        ):
            with pdf.open() as doc, self.assertRaises(UserError):
                draw_number(doc.new_page(), 0, options)
