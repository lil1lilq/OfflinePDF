import tempfile
import unittest
from pathlib import Path

import pymupdf as pdf
from PIL import Image

from offline_pdf.engine import UserError, execute
from offline_pdf.overlays import POSITIONS


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "한글 삽입.pdf"
        with pdf.open() as doc:
            for rotation in (0, 90, 180, 270):
                page = doc.new_page(width=400, height=500)
                page.set_rotation(rotation)
            doc.save(self.source)
        self.stamp = self.root / "투명 직인.png"
        with Image.new("RGBA", (40, 20), (255, 0, 0, 128)) as image:
            image.save(self.stamp)

    def tearDown(self):
        self.temp.cleanup()

    def run_tool(self, tool, **options):
        folder = execute(
            {
                "tool": tool,
                "files": [str(self.source)],
                "output": str(self.root),
                "options": options,
            }
        )
        return next(folder.glob("*.pdf"))

    def test_all_text_positions_on_rotated_pages_are_visible_and_searchable(self):
        for position in POSITIONS:
            with self.subTest(position=position):
                with pdf.open(self.run_tool("watermark", text="HELLO", position=position)) as doc:
                    for page in doc:
                        self.assertIn("HELLO", page.get_text())
                        words = page.get_text("words")
                        rect = pdf.Rect(words[0][:4]) * page.rotation_matrix
                        self.assertTrue(page.rect.contains(rect), (position, page.rotation, rect))

    def test_image_position_proportion_and_combined_alpha_on_rotated_pages(self):
        for position in POSITIONS:
            with self.subTest(position=position):
                with pdf.open(
                    self.run_tool(
                        "stamp",
                        stamp_path=str(self.stamp),
                        stamp_width="100",
                        opacity="0.5",
                        position=position,
                    )
                ) as doc:
                    for page in doc:
                        entry = page.get_images(full=True)[0]
                        self.assertGreater(entry[1], 0)
                        mask = pdf.Pixmap(doc, entry[1])
                        self.assertTrue(all(value == 64 for value in mask.samples))
                        image_rect = page.get_image_rects(entry[0])[0] * page.rotation_matrix
                        self.assertAlmostEqual(image_rect.width, 100, places=3)
                        self.assertAlmostEqual(image_rect.height, 50, places=3)
                        self.assertTrue(page.rect.contains(image_rect))
                        if "위" in position:
                            self.assertAlmostEqual(image_rect.y0, 20, places=3)
                        if "아래" in position:
                            self.assertAlmostEqual(image_rect.y1, page.rect.height - 20, places=3)

    def test_invalid_values_and_oversize_images_leave_no_output(self):
        before = set(self.root.iterdir())
        for options in (
            {"position": "invalid"},
            {"opacity": "nan"},
            {"opacity": "1.1"},
            {"stamp_width": "400"},
            {"stamp_path": str(self.root / "missing.png")},
        ):
            with self.subTest(options=options), self.assertRaises(UserError):
                self.run_tool("stamp", **({"stamp_path": str(self.stamp)} | options))
        self.assertEqual(set(self.root.iterdir()), before)
