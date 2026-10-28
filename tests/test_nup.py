import hashlib
import tempfile
import threading
import unittest
from pathlib import Path

import pymupdf as pdf

from offline_pdf.engine import Cancelled, UserError, execute
from offline_pdf.nup import NupLayout, make_nup


class NupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "원본.pdf"
        with pdf.open() as doc:
            for i in range(10):
                page = doc.new_page(width=400, height=300)
                page.draw_rect(page.rect, fill=(i / 12, 0.4, 0.8), color=None)
                page.insert_text((100, 150), f"PAGE_{i + 1}", fontsize=20)
            doc.save(self.source)
        self.digest = hashlib.sha256(self.source.read_bytes()).digest()

    def tearDown(self):
        self.assertEqual(self.digest, hashlib.sha256(self.source.read_bytes()).digest())
        self.temp.cleanup()

    def run_tool(self, files=None, **options):
        return execute(
            {
                "tool": "nup",
                "files": files or [str(self.source)],
                "output": str(self.root),
                "options": options,
            }
        )

    def test_default_a4_page_count_text_and_vectors(self):
        folder = self.run_tool()
        with pdf.open(next(folder.glob("*.pdf"))) as result:
            self.assertEqual(len(result), 3)
            self.assertEqual(tuple(result[0].rect), (0, 0, 595, 842))
            for sheet, expected in enumerate((range(1, 5), range(5, 9), range(9, 11))):
                text = result[sheet].get_text()
                for n in expected:
                    self.assertIn(f"PAGE_{n}\n", text)
                self.assertEqual(result[sheet].get_images(), [])
                self.assertEqual(len(result[sheet].get_drawings()), len(expected))

    def test_arbitrary_count_selection_order_duplicates_and_landscape(self):
        folder = self.run_tool(
            nup_count="3",
            nup_columns="2",
            nup_orientation="가로",
            pages="10,2,2,1",
        )
        with pdf.open(next(folder.glob("*.pdf"))) as result:
            self.assertEqual(len(result), 2)
            self.assertEqual(tuple(result[0].rect), (0, 0, 842, 595))
            self.assertEqual(result[0].get_text().split(), ["PAGE_10", "PAGE_2", "PAGE_2"])
            self.assertEqual(result[1].get_text().split(), ["PAGE_1"])

    def test_margin_gap_and_vertical_order(self):
        folder = self.run_tool(
            nup_columns="2",
            nup_margin="10",
            nup_gap="5",
            nup_order="세로 우선",
        )
        with pdf.open(next(folder.glob("*.pdf"))) as result:
            bounds = [d["rect"] for d in result[0].get_drawings()]
            self.assertAlmostEqual(bounds[0].x0, 10 * 72 / 25.4, places=3)
            self.assertAlmostEqual(bounds[2].x0 - bounds[0].x1, 5 * 72 / 25.4, delta=0.01)
            self.assertEqual(bounds[0].x0, bounds[1].x0)
            self.assertGreater(bounds[1].y0, bounds[0].y0)
            self.assertGreater(bounds[2].x0, bounds[1].x0)

    def test_fit_preserves_content_and_fill_covers_a4(self):
        with pdf.open(self.source) as source:
            for mode in ("전체 내용 유지", "꽉 채우기 (잘림)"):
                with make_nup(source, [0], {"nup_count": "1", "nup_fit": mode}) as result:
                    pix = result[0].get_pixmap()
                    top = pix.pixel(pix.width // 2, 2)
                    self.assertEqual(top == (255, 255, 255), mode == "전체 내용 유지")
                    self.assertIn("PAGE_1", result[0].get_text())

    def test_rotated_cropped_pages_match_source_appearance(self):
        with pdf.open() as source:
            for rotation in (0, 90, 180, 270):
                page = source.new_page(width=500, height=400)
                page.draw_rect(pdf.Rect(50, 60, 230, 190), fill=(1, 0, 0), color=None)
                page.draw_rect(pdf.Rect(230, 60, 450, 190), fill=(0, 1, 0), color=None)
                page.draw_rect(pdf.Rect(50, 190, 450, 360), fill=(0, 0, 1), color=None)
                page.set_cropbox(pdf.Rect(50, 60, 450, 360))
                page.set_rotation(rotation)
            original_bytes = source.tobytes(no_new_id=True)
            for index in range(4):
                with make_nup(source, [index], {"nup_count": "1"}) as result:
                    src = source[index].get_pixmap()
                    dst = result[0].get_pixmap()
                    drawings = result[0].get_drawings()
                    extent = pdf.Rect()
                    for drawing in drawings:
                        extent |= drawing["rect"]
                    for fx, fy in ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75)):
                        self.assertEqual(
                            src.pixel(int(src.width * fx), int(src.height * fy)),
                            dst.pixel(
                                int(extent.x0 + extent.width * fx),
                                int(extent.y0 + extent.height * fy),
                            ),
                        )
            self.assertEqual(source.tobytes(no_new_id=True), original_bytes)

    def test_blank_pages_and_annotation_form_appearances(self):
        with pdf.open() as source:
            source.new_page()
            page = source.new_page()
            annot = page.add_rect_annot(pdf.Rect(50, 50, 150, 150))
            annot.set_colors(stroke=(1, 0, 0), fill=(1, 0, 0))
            annot.update()
            widget = pdf.Widget()
            widget.field_name = "test"
            widget.field_type = pdf.PDF_WIDGET_TYPE_TEXT
            widget.rect = pdf.Rect(50, 200, 250, 240)
            widget.field_value = "FORM_VALUE"
            page.add_widget(widget)
            with make_nup(source, [0, 1], {"nup_count": "1"}) as result:
                self.assertEqual(len(result), 2)
                self.assertEqual(result[0].get_text(), "")
                self.assertIn("FORM_VALUE", result[1].get_text())
                self.assertTrue(result[1].get_drawings())
                self.assertFalse(list(result[1].widgets() or []))

    def test_preview_sheet_matches_export_and_clamps(self):
        with pdf.open(self.source) as source:
            with make_nup(source, list(range(10)), {}) as full:
                with make_nup(source, list(range(10)), {}, sheet=1) as preview:
                    self.assertEqual(len(preview), 1)
                    self.assertEqual(preview[0].get_pixmap().samples, full[1].get_pixmap().samples)
                with make_nup(source, list(range(10)), {}, sheet=999) as preview:
                    self.assertEqual(preview[0].get_text(), full[2].get_text())

    def test_invalid_settings_leave_no_results(self):
        for settings in (
            {"nup_count": "0"},
            {"nup_count": "65"},
            {"nup_count": "1.5"},
            {"nup_count": "abc"},
            {"nup_columns": "5"},
            {"nup_columns": "-1"},
            {"nup_margin": "nan"},
            {"nup_margin": "-1"},
            {"nup_gap": "inf"},
            {"nup_columns": "4", "nup_gap": "100"},
            {"nup_orientation": "bad"},
            {"nup_fit": "bad"},
            {"nup_order": "bad"},
            {"pages": "11"},
        ):
            with self.subTest(settings=settings), self.assertRaises(UserError):
                self.run_tool(**settings)
            self.assertEqual(list(self.root.glob("PDF결과_*")), [])
            self.assertEqual(list(self.root.glob(".offline-pdf-*")), [])

    def test_cancellation_during_export_rolls_back(self):
        cancel = threading.Event()

        def emit(event):
            if event["type"] == "progress":
                cancel.set()

        with self.assertRaises(Cancelled):
            execute(
                {"tool": "nup", "files": [str(self.source)], "output": str(self.root)}, emit, cancel
            )
        self.assertEqual(list(self.root.glob("PDF결과_*")), [])
        self.assertEqual(list(self.root.glob(".offline-pdf-*")), [])

    def test_batch_files_remain_separate_and_failure_is_atomic(self):
        other = self.root / "다른문서.pdf"
        other.write_bytes(self.source.read_bytes())
        folder = self.run_tool(files=[str(self.source), str(other)])
        self.assertEqual(len(list(folder.glob("*.pdf"))), 2)
        broken = self.root / "손상.pdf"
        broken.write_bytes(b"broken")
        with self.assertRaises(UserError):
            self.run_tool(files=[str(self.source), str(broken)])
        self.assertEqual(list(self.root.glob("PDF결과_*")), [folder])
        self.assertEqual(list(self.root.glob(".offline-pdf-*")), [])

    def test_encrypted_output_inherits_password(self):
        locked = self.root / "암호.pdf"
        with pdf.open(self.source) as source:
            source.save(
                locked, encryption=pdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner"
            )
        folder = execute(
            {
                "tool": "nup",
                "files": [str(locked)],
                "output": str(self.root),
                "passwords": {str(locked): "owner"},
            }
        )
        with pdf.open(next(folder.glob("*.pdf"))) as result:
            self.assertTrue(result.needs_pass)
            self.assertTrue(result.authenticate("owner"))
            self.assertIn("PAGE_1", result[0].get_text())

    def test_auto_layout_and_maximum_count(self):
        with pdf.open(self.source) as source:
            with make_nup(source, [0] * 65, {"nup_count": "64"}) as result:
                self.assertEqual(len(result), 2)
                self.assertEqual(result[0].get_text().count("PAGE_1"), 64)
        layout = NupLayout.from_options({"nup_count": "7"}, pdf.Rect(0, 0, 400, 300))
        self.assertGreaterEqual(layout.columns * layout.rows, 7)
