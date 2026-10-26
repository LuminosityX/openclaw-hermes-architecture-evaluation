#!/usr/bin/env python3
"""Verify the official provider plugin against its explicit registry integrity pin."""
import argparse
import hashlib
import json
from pathlib import Path

from suite import ROOT, require

PIN=ROOT/'evaluation/design/deepseek-plugin-pin.json'


def verify(modules,lock_path):
    pin=json.loads(PIN.read_text())
    package=Path(modules)/pin['package']
    metadata=json.loads((package/'package.json').read_text())
    manifest=json.loads((package/'openclaw.plugin.json').read_text())
    lock=json.loads(Path(lock_path).read_text())
    entry=lock['packages']['node_modules/'+pin['package']]
    require(metadata['version']==pin['version']==entry['version'],'Provider plugin version mismatch')
    require(entry['integrity']==pin['integrity'],'Provider plugin registry integrity mismatch')
    require(manifest['id']==pin['plugin_id'],'Provider plugin identity mismatch')
    return dict(kind='official-provider-plugin-verification',package=pin['package'],version=pin['version'],
                plugin_id=manifest['id'],integrity_matches=True,
                manifest_sha256=hashlib.sha256((package/'openclaw.plugin.json').read_bytes()).hexdigest(),
                runtime_entry_sha256=hashlib.sha256((package/'dist/index.js').read_bytes()).hexdigest(),
                package_lock_sha256=hashlib.sha256(Path(lock_path).read_bytes()).hexdigest())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-modules',type=Path,required=True)
    parser.add_argument('--package-lock',type=Path,required=True)
    args=parser.parse_args()
    try: print(json.dumps(verify(args.runtime_modules,args.package_lock),indent=2))
    except (OSError,ValueError,KeyError,TypeError) as error: parser.exit(1,f'FAIL: {error}\n')


if __name__=='__main__': main()
