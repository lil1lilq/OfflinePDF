"""Include the Windows wheel's codec DLLs, which live outside the package."""

from importlib.metadata import distribution
from pathlib import Path

hiddenimports = ["_pillow_heif"]
binaries = []
for entry in distribution("pillow-heif").files or []:
    source = Path(entry.locate())
    if source.suffix.lower() == ".dll" and source.is_file():
        binaries.append((str(source), "."))
