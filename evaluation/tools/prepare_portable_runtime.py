#!/usr/bin/env python3
"""One exact native Windows runtime, hosted only, from the frozen shared lock."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from campaign import load_plan
from target import verify_installation


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REPOSITORY')!='zyw02/openclaw-hermes-architecture-evaluation' or os.name!='nt':
        raise SystemExit('Portable runtime setup is restricted to the actual native Windows GitHub job')
    parser=argparse.ArgumentParser();parser.add_argument('--prefix',type=Path,required=True);args=parser.parse_args()
    if args.prefix.resolve()!=Path(os.environ['RUNNER_TEMP']).resolve()/'openclaw-portable-runtime':raise SystemExit('Unexpected portable installation prefix')
    root=args.prefix;root.mkdir();lock=Path('evaluation/campaigns/full-20261026/preparation/package-lock-d145b4db4bce.json').read_bytes()
    if hashlib.sha256(lock).hexdigest()!='d145b4db4bce891044af6d2a45819d5cb965160856873858e6c124f249f8ac8a':raise SystemExit('Frozen shared dependency lock changed')
    inventory=json.loads(lock);(root/'package-lock.json').write_bytes(lock)
    (root/'package.json').write_text(json.dumps(dict(name=inventory['name'],private=True,dependencies=inventory['packages']['']['dependencies'])),encoding='utf8')
    node=Path(shutil.which('node')).resolve();npm=Path(shutil.which('npm')).resolve();npm_cli=npm.parent/'node_modules/npm/bin/npm-cli.js'
    if not npm_cli.is_file() or json.loads((npm_cli.parent.parent/'package.json').read_text())['name']!='npm':raise SystemExit('Actual native npm toolchain cannot be verified')
    env=dict(os.environ,npm_config_cache=str(root/'npm-cache'),npm_config_update_notifier='false',npm_config_fund='false',npm_config_audit='false')
    subprocess.run([str(node),str(npm_cli),'ci','--prefix',str(root)],env=env,check=True,timeout=360)
    installation=verify_installation(load_plan()['target'],root/'node_modules',root/'package-lock.json')
    if sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink())>4*1024**3:raise SystemExit('Owned native Windows runtime/cache exceeds 4 GiB')
    (root/'installation.json').write_text(json.dumps(installation)+'\n',encoding='utf8')
    print(json.dumps(dict(native_os=os.name,version=installation['installed_build']['version'],verified=True,local_installation=False)))


if __name__=='__main__':main()
