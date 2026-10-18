"""Regression checks for Windows Git checkout and AI asset integrity."""

import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "offlinepdf_ai_prepare", ROOT / "packaging/prepare_ai_model.py"
)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class AIAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "models"
        shutil.copytree(ROOT / "models", self.root)
        self.previous = prepare.MODEL
        prepare.MODEL = self.root

    def tearDown(self):
        prepare.MODEL = self.previous
        self.temp.cleanup()

    def test_lf_and_windows_crlf_license_are_verified(self):
        license = self.root / "Real-ESRGAN-LICENSE.txt"
        original = license.read_bytes().replace(b"\r\n", b"\n")
        for data in (original, original.replace(b"\n", b"\r\n")):
            with self.subTest(crlf=b"\r\n" in data):
                license.write_bytes(data)
                prepare.verify()

    def test_changed_license_content_is_rejected(self):
        license = self.root / "Real-ESRGAN-LICENSE.txt"
        license.write_bytes(license.read_bytes().replace(b"Xintao Wang", b"Changed Name"))
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            prepare.verify()

    def test_changed_onnx_and_original_weights_are_rejected(self):
        for name in ("realesr-general-x4v3.onnx", "source/realesr-general-x4v3.pth"):
            path = self.root / name
            original = path.read_bytes()
            with self.subTest(asset=name):
                path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    prepare.verify()
                path.write_bytes(original)

    def test_git_windows_checkout_preserves_license_and_model_bytes(self):
        # Exercise Git itself with Windows-style autocrlf, not just Python data.
        repo = Path(self.temp.name) / "repo"
        repo.mkdir()

        def git(*args):
            return subprocess.run(
                ["git", "-C", str(repo), *args],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        git("init")
        shutil.copyfile(ROOT / ".gitattributes", repo / ".gitattributes")
        shutil.copytree(self.root, repo / "models")
        git("-c", "core.autocrlf=true", "add", ".gitattributes", "models")
        shutil.rmtree(repo / "models")
        git("-c", "core.autocrlf=true", "checkout-index", "-a", "-f")
        self.assertNotIn(b"\r\n", (repo / "models/Real-ESRGAN-LICENSE.txt").read_bytes())
        for name in ("realesr-general-x4v3.onnx", "source/realesr-general-x4v3.pth"):
            self.assertEqual((repo / "models" / name).read_bytes(), (self.root / name).read_bytes())
        prepare.MODEL = repo / "models"
        prepare.verify()


if __name__ == "__main__":
    unittest.main()
