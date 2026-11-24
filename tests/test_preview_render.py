"""Viewport fidelity, bounded caches, process cancellation and shutdown."""

import tempfile
import time
import unittest
from pathlib import Path

import pymupdf as pdf

from offline_pdf.preview_render import (
    BASE_PIXELS,
    PreviewCache,
    ViewportRenderer,
    raster_view,
    visible_pixels,
)


class PreviewRenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "source.pdf"
        with pdf.open() as doc:
            for i in range(4):
                page = doc.new_page(width=400, height=600)
                page.draw_rect(page.rect, fill=(i / 4, 0.25, 1 - i / 4))
                page.insert_text((50, 100), "SOURCE", fontsize=26)
            doc.save(self.path)
        self.cache = PreviewCache()
        self.cache.document(str(self.path), "")

    def tearDown(self):
        self.cache.close()
        self.temp.cleanup()

    def test_viewport_size_does_not_grow_with_zoom(self):
        for scale in (1, 2, 4, 5):
            pixels = visible_pixels((400 * scale, 600 * scale), (150, 250), (800, 500))
            raster = raster_view(self.cache.source[0], scale, pixels)
            self.assertLessEqual(raster[2], 802)
            self.assertLessEqual(raster[3], 502)
            self.assertLessEqual(len(raster[4]), 802 * 502 * 3)

    def test_clipped_pixels_match_full_page_at_all_rotations(self):
        page = self.cache.source[0]
        for angle in (0, 90, 180, 270):
            page.set_rotation(angle)
            for scale in (1, 2, 5):
                pixels = visible_pixels(
                    (page.rect.width * scale, page.rect.height * scale), (150, 200), (220, 180)
                )
                x, y, width, height, samples = raster_view(page.get_displaylist(), scale, pixels)
                full = page.get_pixmap(matrix=pdf.Matrix(scale, scale), alpha=False)
                from PIL import Image

                with Image.frombytes("RGB", (full.width, full.height), full.samples) as image:
                    with image.crop((x, y, x + width, y + height)) as region:
                        self.assertEqual(samples, region.tobytes())

    def test_cache_reuses_source_and_base_and_evicts_old_pages(self):
        source = self.cache.source
        self.assertIs(self.cache.document(str(self.path), ""), source)
        entry = self.cache.prepared(0)
        base = entry.thumbnail()
        self.assertLessEqual(base.width * base.height, BASE_PIXELS + base.width + base.height)
        self.assertIs(self.cache.prepared(0).thumbnail(), base)
        self.cache.prepared(1)
        self.cache.prepared(2)
        self.assertEqual(len(self.cache.entries), 2)
        self.assertTrue(entry.document.is_closed)
        self.cache.close()
        self.assertTrue(source.is_closed)

    def test_file_replacement_invalidates_cache_and_numbers_do_not_accumulate(self):
        entry = self.cache.prepared(0, number_options={"start": "1"})
        for _ in range(4):
            self.assertIs(self.cache.prepared(0, number_options={"start": "1"}), entry)
        self.assertEqual(entry.page.get_text().count("1"), 1)
        self.assertNotIn("1", self.cache.source[0].get_text())
        replacement = Path(self.temp.name) / "replacement.pdf"
        with pdf.open() as doc:
            doc.new_page().insert_text((50, 50), "REPLACED")
            doc.save(replacement)
        # Close file handles before replacement so the test also works on Windows.
        self.cache.source.close()
        replacement.replace(self.path)
        self.cache.document(str(self.path), "")
        self.assertTrue(entry.document.is_closed)
        self.assertIn("REPLACED", self.cache.prepared(0).page.get_text())

    def test_worker_rejects_stale_frames_and_closes(self):
        renderer = ViewportRenderer()
        try:
            for i in range(3):
                entry = self.cache.prepared(i)
                revision = renderer.submit(entry, 4, (0, 0, 320, 240))
            deadline = time.monotonic() + 15
            latest = None
            while time.monotonic() < deadline:
                result = renderer.poll()
                if result is not None:
                    latest = result
                    break
                time.sleep(0.01)
            self.assertIsNotNone(latest)
            self.assertEqual(latest[0], revision)
            self.assertIsNotNone(latest[1])
            expected = raster_view(self.cache.prepared(2).page, 4, (0, 0, 320, 240))
            self.assertEqual(latest[1], expected)
            renderer.invalidate()
            self.assertFalse(renderer.pending)
        finally:
            renderer.close()
        self.assertFalse(renderer.process.is_alive())
