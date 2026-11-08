"""One version everywhere, in the project's MAJOR.MINOR.PATCH[.FIX] scheme.

Bump rule (see AGENTS.md and BUILDING.md):
  substantial update -> second number  (1.0.0 -> 1.1.0)
  small update       -> third number   (1.0.0 -> 1.0.1)
  bug fix            -> fourth number  (1.0.0 -> 1.0.0.1)
"""

import re
from pathlib import Path
from unittest import TestCase

from offline_pdf import __version__

ROOT = Path(__file__).resolve().parents[1]


def four_part(version):
    """Windows version resources always use four numbers: 1.0.1 -> (1, 0, 1, 0)."""
    numbers = [int(part) for part in version.split(".")]
    return tuple(numbers + [0] * (4 - len(numbers)))


class VersionTests(TestCase):
    def test_format(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+(\.\d+)?$")
        # A trailing ".0" fix number is written without it: 1.0.1, not 1.0.1.0.
        self.assertFalse(re.fullmatch(r"\d+\.\d+\.\d+\.0", __version__), __version__)

    def test_windows_version_resource_matches(self):
        text = (ROOT / "packaging" / "windows-version.txt").read_text(encoding="utf-8")
        numbers = ", ".join(str(n) for n in four_part(__version__))
        self.assertIn(f"filevers=({numbers})", text)
        self.assertIn(f"prodvers=({numbers})", text)
        self.assertIn(f"StringStruct('FileVersion', '{__version__}')", text)
        self.assertIn(f"StringStruct('ProductVersion', '{__version__}')", text)

    def test_readmes_and_changelog_name_the_version(self):
        self.assertIn(f"**{__version__}**", (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn(f"**{__version__}**", (ROOT / "README.en.md").read_text(encoding="utf-8"))
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"\n## {__version__} · ", changelog)

    def test_four_part_padding(self):
        self.assertEqual(four_part("1.0.1"), (1, 0, 1, 0))
        self.assertEqual(four_part("1.0.0.1"), (1, 0, 0, 1))
