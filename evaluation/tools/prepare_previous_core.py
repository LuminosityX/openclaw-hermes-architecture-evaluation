#!/usr/bin/env python3
"""Install one immutable historical comparison on a disposable GitHub worker only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from target import verify_installation


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REPOSITORY')!='zyw02/openclaw-hermes-architecture-evaluation':
        raise SystemExit('Historical runtime preparation is permitted only in this repository GitHub Actions job')
    parser=argparse.ArgumentParser();parser.add_argument('--purpose',choices=['extension','migration'],default='extension');parser.add_argument('--prefix',type=Path,required=True);parser.add_argument('--metadata',type=Path,required=True);args=parser.parse_args()
    temporary=Path(os.environ['RUNNER_TEMP']).resolve();prefix=args.prefix.resolve()
    if prefix!=temporary/'openclaw-previous-runtime' or args.metadata.resolve()!=temporary/'openclaw-campaign-metadata':
        raise SystemExit('Historical control must stay in the exact owned disposable prefix')
    pin='migration-source-core.json' if args.purpose=='migration' else 'previous-core.json'
    target=json.loads((Path('evaluation/design')/pin).read_text());prefix.mkdir()
    (prefix/'package.json').write_text(json.dumps(dict(name='owned-previous-openclaw-control',private=True,dependencies=dict(openclaw=target['version'])))+'\n')
    subprocess.run(['npm','install','--prefix',str(prefix),'--ignore-scripts=false','--no-audit','--no-fund'],check=True,timeout=240)
    # The published core requires its verified package lifecycle before a
    # read-only mount. Complete that on this disposable host, never in tests.
    lifecycle_env=dict(os.environ,OPENCLAW_STATE_DIR=str(prefix/'owned-lifecycle-state'),OPENCLAW_CONFIG_PATH=str(prefix/'owned-lifecycle-config.json'),
        OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_DISABLE_BUNDLED_PLUGINS='1')
    lifecycle=subprocess.run(['node',str(prefix/'node_modules/openclaw/openclaw.mjs'),'--version'],env=lifecycle_env,capture_output=True,text=True,timeout=40)
    if lifecycle.returncode or target['version'] not in lifecycle.stdout:raise SystemExit('Historical native package lifecycle did not pass its version control: '+lifecycle.stderr[-1000:])
    report=verify_installation(target,prefix/'node_modules',prefix/'package-lock.json')
    report.update(kind='historical-comparison-installation',current_campaign_target=False,
        native_package_lifecycle=dict(returncode=lifecycle.returncode,stdout=lifecycle.stdout[-1000:],stderr=lifecycle.stderr[-1000:]),
        core_cli_sha256=hashlib.sha256((prefix/'node_modules/openclaw/openclaw.mjs').read_bytes()).hexdigest())
    (prefix/'identity.json').write_text(json.dumps(report)+'\n')
    (args.metadata/'previous-core-installation.json').write_text(json.dumps(report)+'\n')
    (args.metadata/'previous-core-package-lock.json').write_bytes((prefix/'package-lock.json').read_bytes())
    paths=[temporary/'openclaw-campaign-runtime',temporary/'openclaw-campaign-cache',prefix]
    usage=subprocess.check_output(['du','-sb',*[str(p) for p in paths if p.exists()]],text=True)
    if sum(int(line.split()[0]) for line in usage.splitlines())>4*1024**3:raise SystemExit('Both hosted core installs and the shared cache exceed the 4 GiB bound')
    print(json.dumps(dict(kind=report['kind'],version=target['version'],source_commit=target['source_commit'],verified=True,local_installation=False)))


if __name__=='__main__':main()
