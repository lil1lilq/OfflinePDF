"""The AGPL Corresponding Source is one archive published beside the program."""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "packaging" / "make_source_archive.py"


class SourceArchiveTests(TestCase):
    def run_script(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True
        )

    def test_holds_app_and_dependency_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            deps = folder / "dependency-sources"
            deps.mkdir()
            (deps / "sources.json").write_text("[]", encoding="utf-8")
            (deps / "mupdf-source.tar.gz").write_bytes(b"archive")
            (deps / "left.partial").write_bytes(b"interrupted download")
            target = folder / "OfflinePDF-1.0.0-source.zip"
            result = self.run_script(target, deps)
            self.assertEqual(result.returncode, 0, result.stderr)
            names = zipfile.ZipFile(target).namelist()
        self.assertIn("OfflinePDF/main.py", names)
        self.assertIn("OfflinePDF/offline_pdf/engine.py", names)
        self.assertIn("dependency-sources/sources.json", names)
        self.assertIn("dependency-sources/mupdf-source.tar.gz", names)
        self.assertNotIn("dependency-sources/left.partial", names)
        self.assertFalse(any("crash-log" in name for name in names))

    def test_refuses_unprepared_dependency_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_script(Path(folder) / "out.zip", Path(folder) / "missing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not prepared", result.stderr + result.stdout)

    def test_release_packages_point_to_the_source_archive(self):
        text = (ROOT / "SOURCE_CODE.txt").read_text(encoding="utf-8")
        self.assertIn("-source.zip", text)
        build = (ROOT / "packaging" / "build_windows.ps1").read_text(encoding="utf-8")
        self.assertIn("'SOURCE_CODE.txt'", build)
        self.assertNotIn("Copy-Item 'dependency-sources'", build)
