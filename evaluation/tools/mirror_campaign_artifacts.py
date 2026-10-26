#!/usr/bin/env python3
"""Mirror validated formal ZIP bytes to persistent GitHub Release assets, hosted only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from campaign import DEFAULT_PLAN,load_plan
from retain_campaign_results import ARTIFACT_LIMIT,REPOSITORY,api,compact_results,bounded_archive
from suite import require

TAG='evidence-full-20261026'
REGISTRY=DEFAULT_PLAN.parent/'permanent-evidence.json'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True,type=int)
    parser.add_argument('--exclude-scenarios',nargs='+',default=[])
    parser.add_argument('--exclusion-reason')
    args=parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REPOSITORY')==REPOSITORY,
        'Raw evidence mirroring runs only on the owned disposable GitHub controller; no local ZIP download')
    metadata=json.loads(api('actions/runs/'+str(args.run_id)))
    require(metadata['status']=='completed' and metadata['head_branch']=='main' and metadata['repository']['full_name']==REPOSITORY,'Only completed owned main runs may be archived')
    artifacts=json.loads(api('actions/runs/'+str(args.run_id)+'/artifacts?per_page=100'))['artifacts']
    registry=json.loads(REGISTRY.read_text()) if REGISTRY.exists() else dict(kind='persistent-github-formal-evidence',release_tag=TAG,assets={},
        scope='Exact validated hosted ZIP bytes, with source run/controller and SHA-256. Accepted coverage comes from the campaign ledger, not archive existence. Validity exclusions remain in hosted-evidence manifests. Raw evidence is never added to the Git checkout.')
    mirrored=[];release=None
    for artifact in artifacts:
        if not artifact['name'].startswith('campaign-'):continue
        require(not artifact['expired'] and artifact['size_in_bytes']<=ARTIFACT_LIMIT,'Raw artifact expired or exceeds its bound')
        payload=api('actions/artifacts/'+str(artifact['id'])+'/zip');files=bounded_archive(payload)
        if 'results.json' not in files and 'execution.json' not in files:continue
        compact_results(load_plan(),metadata,artifact,payload,args.exclude_scenarios,args.exclusion_reason)
        digest=hashlib.sha256(payload).hexdigest();name=str(args.run_id)+'-'+artifact['name']+'-'+digest+'.zip'
        require(re.fullmatch(r'[A-Za-z0-9._-]+',name),'Unsafe release asset name')
        if release is None:
            lookup=subprocess.run(['gh','api','repos/'+REPOSITORY+'/releases/tags/'+TAG],capture_output=True,text=True,timeout=60)
            if lookup.returncode:
                require('404' in lookup.stderr,'Cannot inspect the owned evidence release')
                with tempfile.TemporaryDirectory(prefix='owned-evidence-release-') as directory:
                    notes=Path(directory)/'notes.txt';notes.write_text('Persistent raw evidence for the pinned OpenClaw full campaign. ZIP files are the exact original GitHub Actions artifacts; SHA-256 and controller provenance are recorded in evaluation/campaigns/full-20261026-batched/permanent-evidence.json. Archive presence does not imply scenario acceptance. All test content is synthetic.\n')
                    subprocess.run(['gh','release','create',TAG,'--repo',REPOSITORY,'--target',metadata['head_sha'],'--title','OpenClaw full campaign: raw evidence','--notes-file',str(notes)],check=True,timeout=60)
                release=json.loads(api('releases/tags/'+TAG))
            else:release=json.loads(lookup.stdout)
        assets=json.loads(api('releases/'+str(release['id'])+'/assets?per_page=100'))
        existing=next((asset for asset in assets if asset['name']==name),None)
        if existing is None:
            with tempfile.TemporaryDirectory(prefix='owned-evidence-zip-') as directory:
                path=Path(directory)/name;path.write_bytes(payload)
                subprocess.run(['gh','release','upload',TAG,str(path),'--repo',REPOSITORY],check=True,timeout=120)
            assets=json.loads(api('releases/'+str(release['id'])+'/assets?per_page=100'))
            existing=next((asset for asset in assets if asset['name']==name),None)
        require(existing and existing['state']=='uploaded' and existing['size']==len(payload),'Persistent asset upload has no matching completed receipt')
        # Verify actual stored bytes, including idempotent runs; names alone are not integrity proof.
        stored=subprocess.check_output(['gh','api','repos/'+REPOSITORY+'/releases/assets/'+str(existing['id']),'-H','Accept: application/octet-stream'],timeout=90)
        require(len(stored)<=ARTIFACT_LIMIT and hashlib.sha256(stored).hexdigest()==digest,'Persistent raw asset failed independent readback SHA-256')
        key=str(args.run_id)+'/'+str(artifact['id'])
        entry=dict(github_run_id=str(args.run_id),controller_commit=metadata['head_sha'],source_artifact_id=artifact['id'],
            source_artifact_name=artifact['name'],source_zip_sha256=digest,zip_bytes=len(payload),release_asset_id=existing['id'],
            download_url=existing['browser_download_url'],release_url=release['html_url'],stored_bytes_readback_verified=True)
        if key in registry['assets']:require(registry['assets'][key]==entry,'Persistent archive identity changed')
        registry['assets'][key]=entry;mirrored.append(key)
    if mirrored:REGISTRY.write_text(json.dumps(registry,separators=(',',':'),sort_keys=True)+'\n')
    print(json.dumps(dict(run_id=args.run_id,persistent_assets=mirrored,raw_bytes_added_to_git_checkout=0)))


if __name__=='__main__':main()
