#!/usr/bin/env python3
"""Retain compact formal results; inspect bounded hosted ZIPs in memory only."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

from campaign import DEFAULT_PLAN, audit, load_plan, records_from, validate_result
from suite import ROOT, require

REPOSITORY='zyw02/openclaw-hermes-architecture-evaluation'
ARTIFACT_LIMIT=8*1024**2


def bounded_archive(payload):
    require(len(payload)<=ARTIFACT_LIMIT,'Hosted artifact exceeds its compressed bound')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries=[entry for entry in archive.infolist() if not entry.is_dir()]
        require(sum(entry.file_size for entry in entries)<=ARTIFACT_LIMIT,'Hosted evidence exceeds its expanded bound')
        require(len({entry.filename for entry in entries})==len(entries),'Duplicate archive entries')
        for entry in entries:
            path=PurePosixPath(entry.filename)
            require(not path.is_absolute() and '..' not in path.parts,'Unsafe archive evidence path')
        return {entry.filename:archive.read(entry) for entry in entries}


def compact_results(plan,metadata,artifact,payload,excluded_scenarios=(),exclusion_reason=None):
    require(not excluded_scenarios or exclusion_reason,'Explicit validity exclusion requires a documented reason')
    files=bounded_archive(payload)
    require('results.json' in files and 'execution.json' in files,'Hosted shard did not retain formal result/provenance records')
    execution=json.loads(files['execution.json'])
    require(str(execution['github_run_id'])==str(metadata['id']) and execution['controller_commit']==metadata['head_sha'],
            'Hosted execution provenance disagrees with the run')
    original=json.loads(files['results.json'])
    require(isinstance(original,list) and original,'No formal observations retained')
    url='https://github.com/'+REPOSITORY+'/actions/runs/'+str(metadata['id'])+'/artifacts/'+str(artifact['id'])
    rows=[];exclusions=[]
    for row in original:
        validate_result(row,plan)
        require(row.get('full_campaign_coverage') is True,'Development output cannot enter formal retention')
        require(str(row['run_id'])==str(metadata['id']),'Formal record run mismatch')
        references=row['evidence']
        for reference in references:
            path=reference.split('#',1)[0]
            require(path in files,'Original evidence path is missing: '+path)
            if path.endswith('/summary.json') and row.get('native_summary_sha256'):
                require(hashlib.sha256(files[path]).hexdigest()==row['native_summary_sha256'],'Original native evidence digest mismatch')
        if row['scenario_id'] in excluded_scenarios:
            exclusions.append(dict(scenario_id=row['scenario_id'],unit=row['unit'],original_state=row['state'],
                reason=exclusion_reason,original_evidence=references,original_record_sha256=hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest()))
            continue
        rows.append(dict(row,original_evidence_paths=references,evidence=[url+'#'+ref for ref in references],
                         hosted_artifact_id=artifact['id']))
    manifest=dict(kind='hosted-formal-evidence-manifest',github_run_id=str(metadata['id']),
        workflow_conclusion=metadata.get('conclusion'),execution_harness_failures=execution.get('harness_failures',[]),
        controller_commit=metadata['head_sha'],plan_sha256=plan['plan_sha256'],artifact_id=artifact['id'],
        artifact_name=artifact['name'],artifact_url=url,artifact_zip_sha256=hashlib.sha256(payload).hexdigest(),
        artifact_expires_at=artifact.get('expires_at'),files={path:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for path,data in sorted(files.items())},
        local_raw_evidence_retained=False,record_count=len(rows))
    if exclusions:manifest.update(original_record_count=len(original),validity_exclusions=exclusions)
    return rows,manifest


def api(path):
    return subprocess.check_output(['gh','api','repos/'+REPOSITORY+'/'+path],timeout=60)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',type=int,required=True)
    parser.add_argument('--exclude-scenarios',nargs='+',default=[],help='Quarantine explicitly invalid observations; raw evidence remains in the manifest')
    parser.add_argument('--exclusion-reason',help='Required factual validity incident explanation')
    args=parser.parse_args()
    plan=load_plan()
    metadata=json.loads(api('actions/runs/'+str(args.run_id)))
    require(metadata['status']=='completed','Wait for the hosted run to finish and retain its artifacts')
    artifacts=json.loads(api('actions/runs/'+str(args.run_id)+'/artifacts?per_page=100'))['artifacts']
    pending={};excluded=set()
    for artifact in artifacts:
        if not artifact['name'].startswith('campaign-'):
            continue
        require(not artifact['expired'] and artifact['size_in_bytes']<=ARTIFACT_LIMIT,'Hosted evidence expired or exceeded its bound')
        rows,manifest=compact_results(plan,metadata,artifact,api('actions/artifacts/'+str(artifact['id'])+'/zip'),args.exclude_scenarios,args.exclusion_reason)
        excluded.update(row['scenario_id'] for row in manifest.get('validity_exclusions',[]))
        suffix=str(args.run_id)+'-'+artifact['name']+'.json'
        pending[DEFAULT_PLAN.parent/'results'/suffix]=json.dumps(rows,ensure_ascii=False,separators=(',',':'))+'\n'
        pending[DEFAULT_PLAN.parent/'hosted-evidence'/suffix]=json.dumps(manifest,ensure_ascii=False,separators=(',',':'))+'\n'
    require(pending,'No formal campaign artifacts found')
    require(excluded==set(args.exclude_scenarios),'Requested validity exclusion did not match actual hosted records')
    existing=records_from(DEFAULT_PLAN.parent/'results')
    new=[]
    for path,data in pending.items():
        if path.exists():
            require(path.read_text()==data,'Refusing to overwrite different retained evidence')
        elif path.parent.name=='results':
            new.extend(json.loads(data))
    report=audit(plan,existing+new)
    retained=sum(p.stat().st_size for p in (ROOT/'evaluation/campaigns').rglob('*') if p.is_file())
    additional=sum(len(data.encode()) for path,data in pending.items() if not path.exists())
    require(retained+additional<=plan['resource_policy']['maximum_local_campaign_evidence_bytes'],'Compact retention would exceed the local 4 MiB campaign budget')
    for path,data in pending.items():
        if not path.exists():
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(data)
    print(json.dumps(dict(run_id=args.run_id,new_formal_records=len(new),measured_scenarios=report['measured_scenarios'],
        accepted_observations=report['accepted_observation_count'],remaining_scenarios=len(report['missing_or_invalid_scenarios']),
        analysis_allowed=report['analysis_allowed'],total_local_campaign_bytes=retained+additional)))


if __name__=='__main__':
    main()
