"""Crop direction must agree with the rotated preview and preserve the source."""

import tempfile
import unittest
from pathlib import Path

import pymupdf as pdf

from offline_pdf.crop import MIN_CROP, MM, crop_pages, resized_crop, visible_crop_rect
from offline_pdf.engine import UserError, crop_page_rect, execute


class CropTests(unittest.TestCase):
    def test_asymmetric_crop_matches_display_pixels_at_every_rotation(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.pdf"
            expected = []
            options = {
                f"margin_{side}": str(points / MM)
                for side, points in zip(("left", "top", "right", "bottom"), (30, 40, 50, 60))
            }
            with pdf.open() as doc:
                for rotation in (0, 90, 180, 270):
                    page = doc.new_page(width=400, height=600)
                    for index, color in enumerate(((1, 0, 0), (0, 1, 0), (0, 0, 1), (0.5, 0.5, 0))):
                        page.draw_rect((0, index * 150, 400, (index + 1) * 150), fill=color)
                    page.insert_text((70, 240), f"Rotation {rotation}", fontsize=22)
                    page.set_cropbox(pdf.Rect(10, 20, 390, 580))
                    page.set_rotation(rotation)
                doc.save(source)
            before = source.read_bytes()
            with pdf.open(source) as doc:
                for page in doc:
                    pix = page.get_pixmap(clip=visible_crop_rect(page, options), alpha=False)
                    expected.append((pix.width, pix.height, pix.samples))
            output = execute(
                {"tool": "crop", "files": [str(source)], "output": folder, "options": options}
            )
            with pdf.open(next(output.glob("*.pdf"))) as doc:
                for i, page in enumerate(doc):
                    pix = page.get_pixmap(alpha=False)
                    self.assertEqual((pix.width, pix.height, pix.samples), expected[i])
                    self.assertEqual(page.rotation, (0, 90, 180, 270)[i])
            self.assertEqual(source.read_bytes(), before)

    def test_minimum_clamping_and_each_handle_direction(self):
        rect = pdf.Rect(40, 50, 350, 540)
        bounds = (400, 600)
        base = {"left": 40 / MM, "top": 50 / MM, "right": 50 / MM, "bottom": 60 / MM}
        mapping = {"w": "left", "n": "top", "e": "right", "s": "bottom"}
        with pdf.open() as doc:
            page = doc.new_page(width=400, height=600)
            for handle in ("nw", "n", "ne", "w", "e", "sw", "s", "se"):
                values = resized_crop(rect, handle, 20, -10, bounds)
                changed = {mapping[letter] for letter in handle}
                for side in base.keys() - changed:
                    self.assertAlmostEqual(values[side], base[side], delta=0.011)
                for dx, dy in ((10000, 10000), (-10000, -10000)):
                    values = resized_crop(rect, handle, dx, dy, bounds)
                    crop = visible_crop_rect(
                        page, {f"margin_{side}": value for side, value in values.items()}
                    )
                    self.assertGreaterEqual(crop.width, MIN_CROP - 1e-6)
                    self.assertGreaterEqual(crop.height, MIN_CROP - 1e-6)
                    self.assertTrue(page.rect.contains(crop))

    def test_legacy_uniform_margin_and_validation(self):
        with pdf.open() as doc:
            page = doc.new_page(width=400, height=600)
            self.assertEqual(
                crop_page_rect(page, {"margin": str(10 / MM)}), pdf.Rect(10, 10, 390, 590)
            )
            for value in ("NaN", "inf", "-1", "invalid", "1000"):
                with self.subTest(value=value), self.assertRaises(UserError):
                    crop_page_rect(page, {"margin_left": value})
            self.assertEqual(crop_page_rect(page, {"margin": "0"}), page.cropbox)
        self.assertEqual(crop_pages({"crop_scope": "현재 페이지", "crop_page": "3"}, 5), [2])
        self.assertEqual(crop_pages({"crop_scope": "지정 페이지", "pages": "2,4"}, 5), [1, 3])
        self.assertEqual(crop_pages({"crop_scope": "전체 페이지", "pages": "bad"}, 3), [0, 1, 2])

    def test_current_and_specified_scope_only_change_chosen_pages(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "scope.pdf"
            with pdf.open() as doc:
                for _ in range(3):
                    doc.new_page()
                doc.save(source)
            for options, cropped in (
                ({"crop_scope": "현재 페이지", "crop_page": "2"}, {1}),
                ({"crop_scope": "지정 페이지", "pages": "1,3"}, {0, 2}),
                ({"crop_scope": "전체 페이지", "pages": "bad"}, {0, 1, 2}),
            ):
                output = execute(
                    {
                        "tool": "crop",
                        "files": [str(source)],
                        "output": folder,
                        "options": dict(
                            options,
                            margin_left="5",
                            margin_right="0",
                            margin_top="0",
                            margin_bottom="0",
                        ),
                    }
                )
                with pdf.open(next(output.glob("*.pdf"))) as doc:
                    for i, page in enumerate(doc):
                        self.assertAlmostEqual(
                            page.cropbox.x0, 5 * MM if i in cropped else 0, places=3
                        )
