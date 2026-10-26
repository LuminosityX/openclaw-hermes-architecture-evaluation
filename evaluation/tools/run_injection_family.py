#!/usr/bin/env python3
"""Calibrate both privacy oracle directions, then run the frozen real-model units."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from adapter_readiness import SOURCES,load_proofs,require_execution_ready
from campaign import DEFAULT_PLAN,load_plan,records_from,validate_result
from suite import ROOT,require
from target import verify_installation


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['runtime-modules','node','package-lock','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--mode',choices=['calibration','formal'],required=True)
    parser.add_argument('--case',choices=['SEC-09','PERF-10','COST-03'],default='SEC-09')
    parser.add_argument('--scenarios',nargs='+',help='Only pending formal scenarios; calibration always covers the whole family')
    args=parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.geteuid()==0,'Execution requires the disposable hosted controller')
    plan=load_plan();case=next(c for c in plan['cases'] if c['id']==args.case)
    selected=args.scenarios or [s['id'] for s in case['scenarios']]
    require(len(selected)==len(set(selected)) and set(selected)<={s['id'] for s in case['scenarios']},'Invalid model scenario selection')
    installation=verify_installation(plan['target'],args.runtime_modules,args.package_lock)
    args.output.mkdir(parents=True,exist_ok=True);proofs=args.output/'provenance';proofs.mkdir(exist_ok=True)
    def invoke(sid,unit,directory,control=None):
        command=[sys.executable,str(ROOT/'evaluation/tools/run_task_unit.py'),'--runtime-modules',str(args.runtime_modules),
            '--node',str(args.node),'--package-lock',str(args.package_lock),'--output',str(directory),
            '--scenario',sid,'--unit',str(unit),'--proofs',str(proofs)]
        if control is not None:command+=['--validate-adapter','--scripted-provider','--thinking','disabled']
        if control=='malicious':command+=['--attack-control']
        result=subprocess.run(command,timeout=1300 if args.case=='COST-03' else 1000 if args.case=='PERF-10' else 380,check=False)
        path=directory/'task-result.json'
        row=json.loads(path.read_text()) if path.is_file() else None
        return result.returncode,row
    if args.mode=='calibration':
        observations=[]
        for scenario in case['scenarios']:
            sid=scenario['id'];directory=args.output/'calibration'/sid
            controls=['benign','malicious'] if args.case=='SEC-09' else ['benign']
            for control in controls:
                code,row=invoke(sid,1,directory/control,control)
                require(code==0 and row is not None,'Native '+control+' control failed for '+sid)
                require(row['state']==('pass' if control=='benign' else 'fail'),'Privacy control oracle disagrees for '+sid)
                if control=='benign':benign=row
            assertions=list(benign['assertions'])
            if args.case=='SEC-09':assertions.append(dict(name='leaking-native-transcript-rejected',verdict='pass',evidence=['calibration/'+sid+'/malicious/task-result.json']))
            observations.append(dict(scenario_id=sid,state='pass',native_invoked=True,fixture_validated=True,assertions=assertions))
        proof=dict(kind='native-adapter-validation',case_id=args.case,full_campaign_coverage=False,
            runtime_identity=installation['installed_build'],validation_complete=True,fixture_and_invocation_valid=True,
            observations=observations,paid_model_calls=0,
            controller_sha256={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in SOURCES[args.case]})
        (proofs/('adapter-validation-'+os.environ['GITHUB_RUN_ID']+'-'+args.case+'.json')).write_text(json.dumps(proof,ensure_ascii=False)+'\n')
        require_execution_ready(plan,args.case,load_proofs(proofs))
        return
    require_execution_ready(plan,args.case,load_proofs(proofs))
    accepted=records_from(DEFAULT_PLAN.parent/'results')
    ids=set(selected)
    require(not any(r['scenario_id'] in ids and r['state'] in {'pass','fail'} for r in accepted),'Selected model scenarios already have accepted observations')
    rows=[];failures=[]
    for scenario in case['scenarios']:
        sid=scenario['id']
        if sid not in ids:continue
        for unit in range(1,case['required_independent_units']+1):
            directory=args.output/sid/('unit-'+str(unit))
            try:
                code,row=invoke(sid,unit,directory)
                require(row is not None,'Task controller did not retain a formal record')
                row['evidence']=[str(directory.relative_to(args.output))+'/'+ref for ref in row['evidence']]
                validate_result(row,plan);rows.append(row)
                if code:failures.append(dict(scenario_id=sid,unit=unit,reason='Native task harness failed'))
            except (OSError,ValueError,subprocess.SubprocessError) as error:failures.append(dict(scenario_id=sid,unit=unit,reason=str(error)[:1000]))
            (args.output/'results.json').write_text(json.dumps(rows,ensure_ascii=False,separators=(',',':'))+'\n')
            (args.output/'execution.json').write_text(json.dumps(dict(github_run_id=os.environ['GITHUB_RUN_ID'],
                controller_commit=os.environ['GITHUB_SHA'],case_id=args.case,plan_sha256=plan['plan_sha256'],
                full_campaign_coverage=True,model_execution='real-deepseek-api',harness_failures=failures,
                required_units=case['required_independent_units'],completed_records=len(rows)))+'\n')
    require(not failures,'Some real-model tasks have harness failures; valid results are retained separately')


if __name__=='__main__':main()
