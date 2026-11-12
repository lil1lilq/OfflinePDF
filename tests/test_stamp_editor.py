"""Transparent ink, normalized placement and interactive image editing."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pymupdf as pdf
from PIL import Image, ImageDraw

from offline_pdf.controllers.stamp import resize_rect
from offline_pdf.engine import execute
from offline_pdf.overlays import (
    OverlayError,
    prepare_overlay,
    relative_rect,
    remove_light_background,
)


class StampEngineTests(unittest.TestCase):
    def test_white_paper_transparency_preserves_ink_and_existing_alpha(self):
        with Image.new("RGBA", (80, 60), "white") as image:
            draw = ImageDraw.Draw(image)
            draw.rectangle((20, 20, 30, 30), fill=(0, 0, 0, 255))
            draw.rectangle((40, 20, 50, 30), fill=(220, 0, 0, 128))
            image.putpixel((1, 1), (245, 245, 245, 255))
            with remove_light_background(image, 30) as result:
                self.assertEqual(result.getpixel((0, 0))[3], 0)
                self.assertEqual(result.getpixel((1, 1))[3], 0)
                self.assertEqual(result.getpixel((25, 25)), (0, 0, 0, 255))
                self.assertEqual(result.getpixel((45, 25)), (220, 0, 0, 128))
            self.assertEqual(image.getpixel((0, 0)), (255, 255, 255, 255))

    def test_free_ratio_and_relative_position_in_saved_rotated_mixed_pages(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            stamp = folder / "stamp.png"
            with Image.new("RGBA", (80, 40), (230, 0, 0, 255)) as image:
                image.save(stamp)
            source = folder / "source.pdf"
            with pdf.open() as doc:
                for index, rotation in enumerate((0, 90, 180, 270)):
                    page = doc.new_page(width=400 + index * 30, height=600)
                    page.insert_text((20, 20), "KEEP TEXT")
                    page.set_rotation(rotation)
                doc.save(source)
            original = source.read_bytes()
            box = (0.2, 0.3, 0.7, 0.8)
            result = execute(
                {
                    "tool": "stamp",
                    "files": [str(source)],
                    "output": str(folder),
                    "options": {
                        "stamp_path": str(stamp),
                        "stamp_rect": json.dumps(box),
                        "remove_background": "사용",
                        "pages": "1,3,4",
                    },
                }
            )
            with pdf.open(next(result.glob("*.pdf"))) as doc:
                self.assertFalse(doc[1].get_images())
                for n in (0, 2, 3):
                    page = doc[n]
                    entry = page.get_images()[0]
                    rect = page.get_image_rects(entry[0])[0] * page.rotation_matrix
                    expected = pdf.Rect(
                        box[0] * page.rect.width,
                        box[1] * page.rect.height,
                        box[2] * page.rect.width,
                        box[3] * page.rect.height,
                    )
                    for actual, target in zip(rect, expected):
                        self.assertAlmostEqual(actual, target, places=3)
                    self.assertIn("KEEP TEXT", page.get_text())
            self.assertEqual(source.read_bytes(), original)

    def test_locked_relative_box_preserves_aspect_on_other_page_sizes(self):
        from offline_pdf.overlays import Overlay

        overlay = Overlay(
            "가운데", 1, image=b"image", aspect=2, relative=(0.2, 0.7, 0.8, 0.95), lock_aspect=True
        )
        with pdf.open() as doc:
            for width, height in ((400, 600), (600, 400), (1000, 100)):
                page = doc.new_page(width=width, height=height)
                rect = overlay.image_rect(page)
                self.assertAlmostEqual(rect.width / rect.height, 2)
                self.assertTrue(page.rect.contains(rect))

    def test_background_toggle_opacity_and_source_preservation(self):
        from io import BytesIO

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "stamp.png"
            with Image.new("RGB", (30, 20), "white") as image:
                image.putpixel((15, 10), (0, 0, 0))
                image.save(path)
            original = path.read_bytes()
            for mode, expected in (("사용", 0), ("사용 안 함", 128)):
                overlay = prepare_overlay(
                    {"stamp_path": str(path), "remove_background": mode, "opacity": "0.5"},
                    image=True,
                )
                with Image.open(BytesIO(overlay.image)) as image:
                    self.assertEqual(image.getpixel((0, 0))[3], expected)
                    self.assertEqual(image.getpixel((15, 10))[3], 128)
            self.assertEqual(path.read_bytes(), original)
        for value in ("[0,0,1,2]", "[0,0,0,1]", "[0,0,NaN,1]", "{}"):
            with self.assertRaises(OverlayError):
                relative_rect(value)

    def test_resize_corners_lock_and_page_bounds(self):
        for corner, point in (
            ("nw", (-50, -50)),
            ("ne", (1000, -50)),
            ("se", (1000, 1000)),
            ("sw", (-50, 1000)),
        ):
            x0, y0, x1, y1 = resize_rect((50, 50, 150, 100), corner, point, (300, 400), 2)
            self.assertGreater(x1, x0)
            self.assertGreater(y1, y0)
            self.assertTrue(0 <= x0 < x1 <= 300 and 0 <= y0 < y1 <= 400)
            self.assertAlmostEqual((x1 - x0) / (y1 - y0), 2)
        rect = resize_rect((50, 50, 150, 100), "se", (200, 200), (300, 400))
        self.assertEqual(rect, (50, 50, 200, 200))


class StampEditorGuiTests(unittest.TestCase):
    def setUp(self):
        import customtkinter as ctk

        from offline_pdf.app import App

        try:
            self.root = ctk.CTk()
        except Exception:
            self.skipTest("Desktop unavailable")
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.source = self.folder / "source.pdf"
        with pdf.open() as doc:
            doc.new_page(width=400, height=600)
            doc.new_page(width=400, height=600)
            doc.save(self.source)
        self.stamp = self.folder / "stamp.png"
        with Image.new("RGB", (80, 40), "white") as image:
            ImageDraw.Draw(image).rectangle((15, 10, 65, 30), fill="red")
            image.save(self.stamp)
        self.app = App(self.root)
        self.app.add_paths([str(self.source)])
        self.app.select_tool("watermark")
        self.app.options["insert_mode"].set("이미지")
        self.app.options["stamp_path"].set(str(self.stamp))
        self.root.update()
        self.app.refresh_preview()

    def tearDown(self):
        if hasattr(self, "app"):
            self.app.close()
            self.temp.cleanup()

    def event(self, x, y):
        return SimpleNamespace(
            x=12 + x * self.app.preview_scale - self.app.canvas.canvasx(0),
            y=12 + y * self.app.preview_scale - self.app.canvas.canvasy(0),
        )

    def test_drag_resize_reset_and_original_view_do_not_change_save_settings(self):
        app = self.app
        self.assertTrue(app.preview_panel.winfo_ismapped())
        x0, y0, x1, y1 = app._stamp_box
        centre = ((x0 + x1) / 2, (y0 + y1) / 2)
        app.draw_start(self.event(*centre))
        app.draw_move(self.event(centre[0] - 30, centre[1] - 40))
        app.draw_end(self.event(centre[0] - 30, centre[1] - 40))
        # Tk canvas coordinates round to screen pixels; compare pointer motion
        # at one-pixel accuracy, then verify saved PDF geometry more strictly.
        self.assertAlmostEqual(app._stamp_box[0], x0 - 30, delta=1 / app.preview_scale)
        self.assertTrue(app.options["stamp_rect"].get())
        app.options["stamp_lock"].set("자유변형")
        app.refresh_preview()
        x0, y0, x1, y1 = app._stamp_box
        app.draw_start(self.event(x1, y1))
        app.draw_end(self.event(x1 + 25, y1 + 10))
        self.assertAlmostEqual(
            app._stamp_box[2] - app._stamp_box[0], 125, delta=1 / app.preview_scale
        )
        before = {key: value.get() for key, value in app.options.items()}
        result = execute(
            {
                "tool": "stamp",
                "files": [str(self.source)],
                "output": str(self.folder),
                "options": before,
            }
        )
        with pdf.open(next(result.glob("*.pdf"))) as doc:
            page = doc[0]
            saved = page.get_image_rects(page.get_images()[0][0])[0]
            for actual, expected in zip(saved, app._stamp_box):
                self.assertAlmostEqual(actual, expected, places=3)
        app.toggle_stamp_original()
        app.refresh_preview()
        self.assertEqual(before, {key: value.get() for key, value in app.options.items()})
        app.reset_stamp()
        app.refresh_preview()
        self.assertEqual(app.options["stamp_rect"].get(), "")
        self.assertEqual(app.options["stamp_width"].get(), "100")
        app.options["pages"].set("2")
        app.refresh_preview()
        self.assertFalse(app.canvas.find_withtag("stamp"))
        app.options["insert_mode"].set("문구")
        self.assertEqual(app.effective_tool(), "watermark")
