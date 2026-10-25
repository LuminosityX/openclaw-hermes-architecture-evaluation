"""Validate and bundle evidence. Never include runtime environments or private keys."""
import hashlib
import argparse
import json
from pathlib import Path
import re
import zipfile
from configure_deepseek import configured_key

ROOT=Path(__file__).resolve().parents[1]
allowed=['charts','results','raw','scripts','configs','logs','fixtures']
files=[ROOT/'report.html',ROOT/'RUNBOOK.txt']
if (ROOT/'FULL-RUNBOOK.txt').exists():files.append(ROOT/'FULL-RUNBOOK.txt')
for name in allowed:
    for path in (ROOT/name).rglob('*'):
        if not path.is_file() or path.is_symlink() or '__pycache__' in path.parts:
            continue
        # Hermes profiles and generated Agent workspaces may contain provider state;
        # share only the explicitly synthetic initial fixtures and pilot inputs/output.
        relative=path.relative_to(ROOT)
        if str(relative)=='results/delivery-manifest.json':
            continue
        if name=='fixtures' and not (relative.parts[1].startswith('skills-') or relative.parts[1] in ['manifest.json','real-pilot','mcp-formal-prompt.txt','extended-models','extended-vision']):
            continue
        if name=='fixtures' and relative.parts[1]=='real-pilot' and path.name not in ['orders.csv','task.txt','result.json']:
            continue
        files.append(path)
key=configured_key()
if key:
    secret=key.encode()
    leaked=[str(path.relative_to(ROOT)) for path in files if secret in path.read_bytes()]
    if leaked:
        raise SystemExit('Refusing archive: private credential found in artifact files: '+','.join(leaked))
manifest={'schema_version':1,'private_key_scan_passed':bool(key),'private_key_scan_outputs':'Only pass/fail; no credential values or fingerprints retained.','files':{str(path.relative_to(ROOT)):{'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size} for path in sorted(set(files))}}
manifest_path=ROOT/'results/delivery-manifest.json'
manifest_path.write_text(json.dumps(manifest,indent=2))
files.append(manifest_path)
parser=argparse.ArgumentParser();parser.add_argument('--archive-name',default='first-batch-results.zip');options=parser.parse_args()
if Path(options.archive_name).name!=options.archive_name:raise SystemExit('Archive name must be a filename')
archive=ROOT/options.archive_name
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=7) as bundle:
    for path in sorted(set(files)):
        bundle.write(path,str(path.relative_to(ROOT)))
print(json.dumps({'archive':str(archive),'files':len(set(files)),'bytes':archive.stat().st_size,'credential_scan_passed':bool(key)}))
