"""Bundle the application's corresponding source alongside every executable."""
from pathlib import Path
import sys
import zipfile

root=Path(__file__).resolve().parents[1]
destination=Path(sys.argv[1]).resolve()
excluded={'.git','.venv','__pycache__','dist','build','release','wheelhouse','dependency-sources'}
with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob('*')):
        rel=path.relative_to(root)
        if path.is_file() and not excluded.intersection(rel.parts) and path.suffix != '.pyc':
            archive.write(path,rel)
print(destination)
