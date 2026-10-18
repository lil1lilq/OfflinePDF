import hashlib
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pymupdf as pdf
from PIL import Image

from offline_pdf.engine import Cancelled, UserError, execute
from offline_pdf.enhance import Upscaler


class EnhancementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "한글 경로"
        self.root.mkdir()
        self.source = self.root / "스캔.pdf"
        image = Image.fromarray(
            np.random.default_rng(4).integers(0, 256, (64, 80, 3), dtype=np.uint8)
        )
        stream = BytesIO()
        image.save(stream, format="PNG")
        image.close()
        with pdf.open() as doc:
            page = doc.new_page(width=240, height=200)
            xref = page.insert_image(pdf.Rect(0, 0, 160, 128), stream=stream.getvalue())
            page.insert_text((10, 175), "SEARCHABLE TEXT")
            page2 = doc.new_page(width=240, height=200)
            page2.insert_image(pdf.Rect(0, 0, 160, 128), xref=xref)
            doc.save(self.source)
        self.digest = hashlib.sha256(self.source.read_bytes()).digest()

    def tearDown(self):
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).digest(), self.digest)
        self.tmp.cleanup()

    def run_tool(self, tool, **options):
        return execute(
            {
                "tool": tool,
                "files": [str(self.source)],
                "output": str(self.root),
                "options": options,
            }
        )

    def test_real_cpu_model_2x_4x_preserves_pdf_text_and_shared_image(self):
        for scale in (2, 4):
            folder = self.run_tool("upscale", scale=str(scale))
            with pdf.open(next(folder.glob("*.pdf"))) as doc:
                self.assertEqual(len(doc), 2)
                self.assertIn("SEARCHABLE TEXT", doc[0].get_text())
                self.assertEqual(doc[0].rect, pdf.Rect(0, 0, 240, 200))
                for page in doc:
                    real = [im for im in page.get_images() if im[2] >= 80 * scale]
                    self.assertTrue(real)
                    self.assertEqual(real[0][2:4], (80 * scale, 64 * scale))

    def test_compression_presets_keep_text_and_reduce_high_resolution_image(self):
        large = self.root / "큰 스캔.pdf"
        data = BytesIO()
        Image.new("RGB", (1600, 1200), "lightgray").save(data, format="PNG")
        with pdf.open() as doc:
            p = doc.new_page(width=144, height=108)
            p.insert_image(p.rect, stream=data.getvalue())
            p.insert_text((5, 20), "KEEP", fontsize=8)
            doc.save(large)
        sizes = []
        for level in ("무손실", "선명하게", "권장", "작게"):
            out = execute(
                {
                    "tool": "compress",
                    "files": [str(large)],
                    "output": str(self.root),
                    "options": {"compression": level},
                }
            )
            with pdf.open(next(out.glob("*.pdf"))) as doc:
                self.assertIn("KEEP", doc[0].get_text())
                sizes.append(doc[0].get_images()[0][2:4])
        self.assertEqual(sizes[0], (1600, 1200))
        self.assertGreater(sizes[1][0], sizes[2][0])
        self.assertGreater(sizes[2][0], sizes[3][0])

    def test_actual_ai_comparison_crop(self):
        folder = self.run_tool("upscale", scale="2", preview_only=True)
        with Image.open(folder / "before.png") as before, Image.open(folder / "after.png") as after:
            self.assertEqual(before.size, after.size)
            self.assertNotEqual(before.tobytes(), after.tobytes())
        self.assertFalse(list(folder.glob("*.pdf")))

    def test_model_matches_numpy_reference_without_pytorch(self):
        import onnx
        from onnx import numpy_helper

        from offline_pdf.enhance import model_folder

        # Independently evaluate every trained layer, including PReLU and PixelShuffle.
        model = onnx.load(model_folder() / "realesr-general-x4v3.onnx")
        weights = {w.name: numpy_helper.to_array(w) for w in model.graph.initializer}
        original = np.random.default_rng(7).random((1, 3, 3, 4), dtype=np.float32)
        value = original.copy()
        indices = sorted({int(k.split(".")[1]) for k in weights if k.startswith("body.")})
        for i in indices:
            key = f"body.{i}"
            w = weights[key + ".weight"]
            if w.ndim == 4:
                windows = np.lib.stride_tricks.sliding_window_view(
                    np.pad(value, ((0, 0), (0, 0), (1, 1), (1, 1))), (3, 3), axis=(2, 3)
                )
                value = (
                    np.einsum("ncyxij,ocij->noyx", windows, w, optimize=True)
                    + weights[key + ".bias"][None, :, None, None]
                )
            else:
                value = np.where(value >= 0, value, value * w)
        n, c, h, w = value.shape
        expected = (
            value.reshape(n, 3, 4, 4, h, w).transpose(0, 1, 4, 2, 5, 3).reshape(n, 3, h * 4, w * 4)
        )
        expected += original.repeat(4, 2).repeat(4, 3)
        actual = Upscaler().session.run(["output"], {"input": original})[0]
        np.testing.assert_allclose(actual, expected, rtol=2e-4, atol=2e-4)

    def test_tiling_has_no_boundary_change(self):
        u = Upscaler()
        a = np.random.default_rng(9).integers(0, 256, (18, 140, 3), dtype=np.uint8)
        with Image.fromarray(a) as image, u.image(image, 4) as tiled:
            tensor = a.astype(np.float32).transpose(2, 0, 1)[None] / 255
            expected = u.session.run(["output"], {"input": np.ascontiguousarray(tensor)})[0]
            expected = np.clip(np.rint(expected[0].transpose(1, 2, 0) * 255), 0, 255).astype(
                np.uint8
            )
            self.assertLessEqual(
                np.max(np.abs(np.asarray(tiled).astype(int) - expected.astype(int))), 1
            )

    def test_limit_cancel_missing_model_and_bad_settings_rollback(self):
        with patch("offline_pdf.enhance.MAX_OUTPUT_PIXELS", 100):
            with self.assertRaises(UserError):
                self.run_tool("upscale", scale="4")
        with patch("offline_pdf.enhance.model_folder", return_value=self.root):
            with self.assertRaises(UserError):
                self.run_tool("upscale", scale="2")
        for tool, options in [("compress", {"compression": "bad"}), ("upscale", {"scale": "3"})]:
            with self.assertRaises(UserError):
                self.run_tool(tool, **options)

        class Cancel:
            def is_set(self):
                return True

        with self.assertRaises(Cancelled):
            execute(
                {"tool": "upscale", "files": [str(self.source)], "output": str(self.root)},
                cancel=Cancel(),
            )
        self.assertFalse(list(self.root.glob(".offline-pdf-*")))
        self.assertFalse(list(self.root.glob("PDF결과_*")))

    def test_different_input_passwords_preserved_and_merge_requires_output_password(self):
        paths = []
        for i, password in enumerate(("first", "second")):
            path = self.root / f"잠김{i}.pdf"
            with pdf.open(self.source) as doc:
                doc.save(
                    path, encryption=pdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password
                )
            paths.append(str(path))
        job = {
            "tool": "compress",
            "files": paths,
            "output": str(self.root),
            "passwords": dict(zip(paths, ("first", "second"))),
            "options": {"compression": "무손실"},
        }
        folder = execute(job)
        for path, password in zip(sorted(folder.glob("*.pdf")), ("first", "second")):
            with pdf.open(path) as doc:
                self.assertTrue(doc.needs_pass)
                self.assertTrue(doc.authenticate(password))
        job["tool"] = "merge"
        with self.assertRaises(UserError):
            execute(job)
        job["options"]["output_password"] = "merged"
        folder = execute(job)
        with pdf.open(next(folder.glob("*.pdf"))) as doc:
            self.assertTrue(doc.authenticate("merged"))
            self.assertEqual(len(doc), 4)


if __name__ == "__main__":
    unittest.main()
