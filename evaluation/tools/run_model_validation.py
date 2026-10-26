#!/usr/bin/env python3
"""Keep the real credential outside the native Gateway's isolated namespace."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

from model_relay import Relay
from suite import ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-modules',type=Path,required=True)
    parser.add_argument('--node',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    key=os.environ.pop('DEEPSEEK_API_KEY','')
    if not key: parser.error('DEEPSEEK_API_KEY is not configured')
    if os.geteuid()!=0: parser.error('Hosted namespace/cgroup controller requires root')
    args.output.mkdir(exist_ok=False,parents=True)
    with tempfile.TemporaryDirectory(prefix='openclaw-host-relay-') as directory:
        relay=Relay(Path(directory)/'provider.sock',key)
        key=''
        thread=threading.Thread(target=relay.serve_forever,daemon=True)
        thread.start()
        try:
            result=subprocess.run([sys.executable,str(ROOT/'evaluation/tools/run_local.py'),
                '--runtime-modules',str(args.runtime_modules),'--node',str(args.node),
                '--output',str(args.output/'native'),'--hosted-profile','--memory-mib','3072',
                '--timeout','300','--model-validation','--relay-socket',str(relay.path)],
                env=dict(os.environ),timeout=330,check=False)
        finally:
            relay.shutdown()
            thread.join(timeout=3)
            relay.write_ledger(args.output/'provider-usage.json')
            relay.server_close()
        if result.returncode: parser.exit(result.returncode,'Native provider plumbing validation failed\n')
        records=json.loads((args.output/'provider-usage.json').read_text())
        if not records['requests'] or not all(r['usage_complete'] and r['upstream_status']==200 for r in records['requests']):
            parser.exit(1,'Usage attribution plumbing is incomplete; no campaign results awarded\n')
        print(json.dumps(dict(kind='real-provider-plumbing-validated',full_campaign_coverage=False,
                              request_count=records['request_count'],usage_ledger=str(args.output/'provider-usage.json'))))


if __name__=='__main__': main()
