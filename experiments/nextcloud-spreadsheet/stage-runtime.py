"""Stage the installed Nextcloud Office libraries for the disposable native probe."""
from pathlib import Path
import argparse
import shutil
parser=argparse.ArgumentParser()
parser.add_argument('--app',type=Path,default=Path('/Applications/Nextcloud Office.app'))
parser.add_argument('--runtime',type=Path,default=Path('/private/tmp/spreadsheet-engines/runtime'))
a=parser.parse_args()
source=a.app/'Contents/Resources/converter'
if not (source/'libdoctrenderer.dylib').is_file(): raise SystemExit('Expected Nextcloud Office macOS library is missing')
a.runtime.mkdir(parents=True,exist_ok=False)
for file in source.iterdir():
    if file.name in ['DoctRenderer.config','fonts.log','AllFonts.js','font_selection.bin']: continue
    (a.runtime/file.name).symlink_to(file.resolve())
for name in ['AllFonts.js','font_selection.bin']: shutil.copy2(source/name,a.runtime/name)
config=(source/'DoctRenderer.config').read_text()
resources=(a.app/'Contents/Resources').resolve()
config=config.replace('../editors',str(resources/'editors')).replace('../dictionaries',str(resources/'dictionaries'))
config=config.replace(str(resources/'editors/sdkjs/common/AllFonts.js'),str((a.runtime/'AllFonts.js').resolve()))
(a.runtime/'DoctRenderer.config').write_text(config)
print(a.runtime)
