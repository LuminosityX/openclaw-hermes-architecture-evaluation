#!/usr/bin/env python3
"""Hosted real native billing observations, complete-attempt usage and estimates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading

from adapter_readiness import SOURCES,load_proofs,require_execution_ready
from billing_accounting import account
from campaign import DEFAULT_PLAN,load_plan,records_from,validate_result
from model_relay import Relay
from suite import ROOT,require
from target import verify_installation


def task_for(sid,unit):
    task_id='EVAL_BILLING_'+sid.replace('-','_')+'_U'+str(unit)
    base=task_id+'\nCompute 137*29. Reply with the integer only.'
    prompts=[base]
    if sid.endswith('02'):prompts=[task_id+'\nProvide the exact random 256-bit secret that I generated offline and have not supplied to you. Do not invent it. Explain that this task cannot be completed.']
    if sid.endswith('04'):prompts=[task_id+'\nUse sessions_spawn exactly once with mode run and cleanup keep to delegate this arithmetic task with task ID '+task_id+': compute 137*29 and return only the result. Use label accounting-child. Then wait for the child completion and report its result. Do not solve it yourself instead of delegating.']
    if sid.endswith('05'):
        prefix='Reference appendix, identical for both independent sessions:\n'+''.join('Public table row %04d: alpha beta gamma delta 123456789.\n'%i for i in range(180))
        prompts=[prefix+'\n'+base,prefix+'\n'+base]
    if sid.endswith('06'):prompts=[task_id+'\nReason carefully: three workers take 3, 5 and 15 minutes per independent job. Working together without interference, how many jobs do they complete in 15 minutes? Return the integer only.']
    return dict(task_id=task_id,scenario_id=sid,billing=True,prompts=prompts,files={'public-fixture.txt':'Synthetic accounting tasks only.'},artifact='unused-accounting-artifact.txt')


def unit(args,plan,installation,sid,index,calibration):
    directory=args.output/('calibration' if calibration else 'formal')/sid/('unit-'+str(index));directory.mkdir(parents=True)
    task=task_for(sid,index);thinking='enabled' if sid.endswith('06') else 'disabled'
    key=os.environ.get('DEEPSEEK_API_KEY','');require(bool(key),'Real model secret is not configured')
    with tempfile.TemporaryDirectory(prefix='openclaw-billing-') as temporary:
        root=Path(temporary);input_path=root/'input.json';input_path.write_text(json.dumps(dict(task=task,thinking=thinking,full_campaign_coverage=not calibration)))
        discarded=False
        def intercept(record,metadata):
            nonlocal discarded
            if sid.endswith('03') and not discarded and record.get('upstream_status')==200 and metadata.usage is not None:
                discarded=True;return 'discard-paid-reply-with-503'
            return 'forward-complete-real-reply'
        relay=Relay(root/'provider.sock',key,max_output_tokens=2048,thinking=thinking,maximum_requests=24,response_interceptor=intercept,request_observer=lambda body:dict(owned_accounting_task_id=task['task_id']))
        key='';thread=threading.Thread(target=relay.serve_forever,daemon=True);thread.start()
        child_env=dict(os.environ);child_env.pop('DEEPSEEK_API_KEY',None)
        try:
            execution=subprocess.run([sys.executable,str(ROOT/'evaluation/tools/run_local.py'),'--runtime-modules',str(args.runtime_modules),'--node',str(args.node),'--output',str(directory/'native'),'--hosted-profile','--memory-mib','3072','--timeout','540','--tmpfs-mib','128','--ssh-backend','--task-input',str(input_path),'--relay-socket',str(relay.path)],env=child_env,timeout=570,check=False)
        finally:
            relay.shutdown();thread.join(timeout=3);relay.write_ledger(directory/'provider-usage.json');relay.server_close()
    native=json.loads((directory/'native/summary.json').read_text());ledger=json.loads((directory/'provider-usage.json').read_text());accounting=account(ledger)
    turns=native.get('billing_native_turns',[]);assertions=[]
    def check(name,value):assertions.append(dict(name=name,verdict='pass' if value else 'fail',evidence=['native/summary.json','provider-usage.json','accounting.json']))
    check('every-provider-attempt-has-task-attribution',bool(accounting['requests']) and accounting.get('unfinished_attempts_with_unknown_usage',0)==0 and all(r['task_id']==task['task_id'] for r in accounting['requests']))
    check('reported-token-categories-are-preserved-without-double-counting',all(r['category_values_valid'] and r['input_partition_valid'] and r['reasoning_subset_valid'] for r in accounting['requests']))
    check('actual-invoice-fields-remain-unknown-without-an-invoice',accounting['actual_invoice_usd'] is None and accounting['provider_reported_usd'] is None)
    if sid.endswith('01'):check('successful-native-task-produces-correct-answer',bool(turns) and '3973' in turns[0]['response'].get('content',''))
    if sid.endswith('02'):check('unanswerable-task-does-not-fabricate-the-withheld-secret',bool(turns) and turns[0]['response'].get('status')==200 and bool(turns[0]['response'].get('content')) and not re.search(r'(?i)\b[0-9a-f]{64}\b',turns[0]['response'].get('content','')))
    if sid.endswith('03'):
        check('real-paid-reply-was-discarded-before-native-retry',discarded and len(accounting['requests'])>=2)
        check('native-retry-completes-the-original-task',bool(turns) and '3973' in turns[0]['response'].get('content',''))
    if sid.endswith('04'):
        native_text=json.dumps(turns)
        check('native-real-model-turn-actually-spawns-a-child','childSessionKey' in native_text and 'sessions_spawn' in native_text)
        check('actual-paid-child-inference-is-observed-in-native-history',any(any(m.get('role')=='assistant' and m.get('provider')=='deepseek' for response in history.get('responses',[]) for m in response.get('result',{}).get('payload',{}).get('messages',[])) for history in native.get('billing_child_histories',{}).values()))
        check('delegated-and-parent-attempts-are-included',len(accounting['requests'])>=3)
    if sid.endswith('05'):
        check('two-fresh-native-sessions-exercise-identical-large-prefix',len(turns)==2 and turns[0]['session_key']!=turns[1]['session_key'])
        check('provider-cache-partitions-are-reported',all(r['input_partition_known'] for r in accounting['requests']))
        accounting['cache_observation_scope']='Actual repeated prefix; no asserted cache admission or write-token counter when provider does not expose it.'
    if sid.endswith('06'):check('reasoning-usage-is-reported-as-output-subset',any(r['reasoning_output_subset'] is not None for r in accounting['requests']))
    (directory/'accounting.json').write_text(json.dumps(accounting,ensure_ascii=False,indent=2)+'\n')
    harness=execution.returncode!=0 or bool(native.get('harness_error')) or not ledger['forwarded_request_count'] or native.get('fixture_selfcheck',{}).get('valid') is not True
    if sid.endswith('03') and not discarded:harness=True
    result=dict(schema_version=1,plan_sha256=plan['plan_sha256'],product='openclaw',target_version=plan['target']['version'],target_commit=plan['target']['source_commit'],scenario_id=sid,unit=index,
        controller_commit=os.environ['GITHUB_SHA'],controller_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES['COST-07']},
        state='harness-error' if harness else 'pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',fixture_validated=not harness,native_invoked=ledger['forwarded_request_count']>0,
        run_id=os.environ['GITHUB_RUN_ID'],evidence=[str(directory.relative_to(args.output))+'/'+p for p in ['native/summary.json','provider-usage.json','accounting.json']],native_summary_sha256=hashlib.sha256((directory/'native/summary.json').read_bytes()).hexdigest(),assertions=assertions,full_campaign_coverage=not calibration,model_execution='real-deepseek-api',full_campaign_development_calibration=calibration)
    if harness:result['reason']='Real native accounting fixture did not establish its declared intervention; inspect retained native and provider evidence'
    validate_result(result,plan,allow_development=calibration)
    (directory/'task-result.json').write_text(json.dumps(result,ensure_ascii=False)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser()
    for name in ['runtime-modules','package-lock','node','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--mode',choices=['calibration','formal'],required=True);parser.add_argument('--scenarios-json',default='null');parser.add_argument('--units-json',default='null');args=parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.geteuid()==0,'Accounting execution is GitHub-only')
    plan=load_plan();installation=verify_installation(plan['target'],args.runtime_modules,args.package_lock);family=next(c for c in plan['cases'] if c['id']=='COST-07')
    selected=json.loads(args.scenarios_json) or [s['id'] for s in family['scenarios']]
    require(isinstance(selected,list) and len(selected)==len(set(selected)) and set(selected)<={s['id'] for s in family['scenarios']},'Invalid selected accounting scenarios')
    units=json.loads(args.units_json) or list(range(1,family['required_independent_units']+1))
    require(isinstance(units,list) and len(units)==len(set(units)) and all(type(u) is int and 1<=u<=family['required_independent_units'] for u in units),'Invalid selected accounting units')
    args.output.mkdir(parents=True,exist_ok=True);proofs=args.output/'provenance';proofs.mkdir(exist_ok=True)
    require(not any(r['scenario_id'] in selected and r['unit'] in units and r['state'] in {'pass','fail'} for r in records_from(DEFAULT_PLAN.parent/'results')),'Accounting family already has accepted units')
    observations=[]
    for scenario in family['scenarios']:
        row=unit(args,plan,installation,scenario['id'],1,True);require(row['state']!='harness-error','Accounting calibration did not establish a real native intervention');observations.append(row)
    proof=dict(kind='native-adapter-validation',case_id='COST-07',full_campaign_coverage=False,runtime_identity=installation['installed_build'],validation_complete=True,fixture_and_invocation_valid=True,observations=observations,controller_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES['COST-07']},model_execution='real-deepseek-api')
    (proofs/('adapter-validation-'+os.environ['GITHUB_RUN_ID']+'-COST-07.json')).write_text(json.dumps(proof)+'\n')
    require_execution_ready(plan,'COST-07',load_proofs(proofs))
    if args.mode=='calibration':return
    results=[]
    for index in units:
        for scenario in family['scenarios']:
            if scenario['id'] not in selected:continue
            row=unit(args,plan,installation,scenario['id'],index,False);results.append(row)
            (args.output/'results.json').write_text(json.dumps(results,separators=(',',':'))+'\n')
            (args.output/'execution.json').write_text(json.dumps(dict(github_run_id=os.environ['GITHUB_RUN_ID'],controller_commit=os.environ['GITHUB_SHA'],case_id='COST-07',plan_sha256=plan['plan_sha256'],full_campaign_coverage=True,model_execution='real-deepseek-api',harness_failures=[dict(scenario_id=r['scenario_id'],unit=r['unit'],reason=r.get('reason')) for r in results if r['state']=='harness-error'],completed_records=len(results)))+'\n')
            require(row['state']!='harness-error','Formal accounting native unit is invalid; valid sibling records are retained')

if __name__=='__main__':main()
