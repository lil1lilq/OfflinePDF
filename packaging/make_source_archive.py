"""Bundle the application's corresponding source alongside every executable.

In a git checkout only tracked files are included, so local leftovers such as
crash dumps or test documents on the build PC never end up in the archive.
A tree without git (rebuilt from this archive) is walked instead, skipping
build output and the same personal-data patterns that .gitignore excludes.
"""

import fnmatch
import subprocess
import sys
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
destination = Path(sys.argv[1]).resolve()
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".ruff_cache",
    "dist",
    "build",
    "release",
    "wheelhouse",
    "dependency-sources",
}
EXCLUDED_FILES = ("crash-log*.txt", "*.dmp", "*.pdf", "*.pyc", "*.spec")


def tracked_files():
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return sorted(name for name in listing.decode("utf-8").split("\0") if name)


def walked_files():
    names = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if not path.is_file() or EXCLUDED_DIRS.intersection(rel.parts):
            continue
        if any(fnmatch.fnmatch(path.name.lower(), pattern) for pattern in EXCLUDED_FILES):
            continue
        names.append(rel.as_posix())
    return names


names = tracked_files()
if names is None:
    print("git is unavailable; archiving the source tree without build output.")
    names = walked_files()
with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
    for name in names:
        path = root / name
        if path.is_file():
            archive.write(path, name)
print(destination)
