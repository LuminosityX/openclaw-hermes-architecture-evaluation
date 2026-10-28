#!/usr/bin/env python3
"""Fetch exact public versioned support contracts on the disposable host only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.request import urlopen


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REPOSITORY')!='zyw02/agent-architecture-evaluation':
        raise SystemExit('Capability contract preparation is hosted-only')
    parser=argparse.ArgumentParser();parser.add_argument('--prefix',type=Path,required=True);args=parser.parse_args()
    expected=Path(os.environ['RUNNER_TEMP']).resolve()/'openclaw-campaign-runtime/native-capability-contracts'
    if args.prefix.resolve()!=expected:raise SystemExit('Contract sources must stay in the exact owned hosted runtime prefix')
    pin=json.loads(Path('evaluation/design/native-budget-contracts.json').read_text());expected.mkdir()
    for entry in pin['contracts']:
        url='https://raw.githubusercontent.com/openclaw/openclaw/'+pin['target_commit']+'/'+entry['path']
        with urlopen(url,timeout=20) as response:raw=response.read(512*1024+1)
        if len(raw)!=entry['bytes'] or hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise SystemExit('Versioned support contract digest mismatch: '+entry['path'])
        (expected/Path(entry['path']).name).write_bytes(raw)
    (expected/'manifest.json').write_text(json.dumps(pin)+'\n')
    print(json.dumps(dict(verified_contract_files=len(pin['contracts']),target_commit=pin['target_commit'],local_runtime_installation=False)))


if __name__=='__main__':main()
