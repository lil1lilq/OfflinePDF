"""Collect exact dependency notices from the build environment, without network."""
from pathlib import Path
import importlib.metadata as metadata
import shutil
import sys
import tkinter

out=Path('licenses');out.mkdir(exist_ok=True)
for name in ['PyMuPDF','Pillow','pillow-heif','pyinstaller','pyinstaller-hooks-contrib']:
    dist=metadata.distribution(name)
    target=out/name;target.mkdir(exist_ok=True)
    for entry in dist.files or []:
        low=str(entry).lower()
        if any(word in Path(low).name for word in ('license','copying','notice')) and entry.locate().is_file():
            # Preserve relative structure to avoid colliding license names.
            path=target/str(entry).replace('../','parent/')
            path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(entry.locate(),path)
    (target/'METADATA.txt').write_text(dist.read_text('METADATA') or '',encoding='utf-8')
python_license=Path(sys.base_prefix)/'LICENSE.txt'
if python_license.is_file():shutil.copyfile(python_license,out/'Python-LICENSE.txt')
tcl=tkinter.Tcl()
for kind,directory in [('Tcl',Path(tcl.eval('info library'))),('Tk',Path(sys.base_prefix)/'tcl'/'tk8.6')]:
    for candidate in [directory/'license.terms',directory/'license.txt']:
        if candidate.is_file():shutil.copyfile(candidate,out/f'{kind}-license.terms');break
(out/'BUILD_COMPONENTS.txt').write_text('\n'.join(f'{dist.metadata["Name"]}=={dist.version}' for dist in metadata.distributions()),encoding='utf-8')
print('Collected dependency notices into licenses/. Review before distribution.')
