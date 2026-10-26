#!/usr/bin/env python3
"""Read the completed Linux job artifact through authenticated GitHub tooling."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true':raise SystemExit('Cross-OS evidence transfer is hosted-only')
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.resolve()!=Path(os.environ['RUNNER_TEMP']).resolve()/'cross-os-source-input':raise SystemExit('Unexpected owned source-artifact destination')
    prefix='repos/zyw02/openclaw-hermes-architecture-evaluation/'
    artifacts=json.loads(subprocess.check_output(['gh','api',prefix+'actions/runs/'+os.environ['GITHUB_RUN_ID']+'/artifacts?per_page=100']))['artifacts']
    selected=[a for a in artifacts if a['name']=='cross-os-native-linux-source' and not a['expired']]
    if len(selected)!=1 or selected[0]['size_in_bytes']>8*1024**2:raise SystemExit('Actual source artifact is unavailable or exceeds its bound')
    raw=subprocess.check_output(['gh','api',prefix+'actions/artifacts/'+str(selected[0]['id'])+'/zip'])
    if len(raw)>8*1024**2:raise SystemExit('Source artifact compressed bound')
    args.output.mkdir()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files=[v for v in archive.infolist() if not v.is_dir()]
        if sum(v.file_size for v in files)>8*1024**2:raise SystemExit('Source artifact expanded bound')
        if len({v.filename for v in files})!=len(files):raise SystemExit('Duplicate source-artifact path')
        for entry in files:
            if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{0,100}',entry.filename):raise SystemExit('Only flat owned native source files may cross hosts')
            (args.output/entry.filename).write_bytes(archive.read(entry))
    (args.output/'source-artifact-provenance.json').write_text(json.dumps(dict(artifact_id=selected[0]['id'],zip_sha256=hashlib.sha256(raw).hexdigest(),run_id=os.environ['GITHUB_RUN_ID'],source_job='actual Linux native baseline'))+'\n')
    print('Verified and transferred bounded actual Linux baseline evidence')


if __name__=='__main__':main()
