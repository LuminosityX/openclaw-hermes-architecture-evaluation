"""Frozen D05 includes all training/auxiliary costs and complete profile resources."""
import json,sys
from pathlib import Path
from runtime import R,save
D=Path('/root/output/oc-hermes-formal-design-20261024');sys.path.insert(0,str(D))
from score_protocol import score

def load(n):return json.loads((R/'results'/(n+'.json')).read_text())
def main():
 profiles=load('reuse') if (R/'results/reuse.json').exists() else []
 if len(profiles)!=12:print('D05_WAITING_COMPLETE_REUSE',len(profiles),'/12');return
 from audit_new_usage import main as reconcile_new
 reconcile_new();receipts={x['run']:x for x in load('additional-usage-reconciliation')};formal=load('current-comparison');obs=load('observations');fee=[];ram=[];cpu=[];descriptive=[]
 for row in formal['pairs']:
  common=dict(unit=f"{row['task']}-v{row['variant']}-r{row['repeat']}",cluster=f"{row['task']}-v{row['variant']}",case=row['task'])
  fee.append(dict(**common,oc=row['cost_oc'],hermes=row['cost_hermes']));ram.append(dict(**common,oc=row['memory_MiB_oc'],hermes=row['memory_MiB_hermes']));cpu.append(dict(**common,oc=row['cpu_seconds_oc'],hermes=row['cpu_seconds_hermes']))
 for u in range(1,7):
  values={}
  for family in ['openclaw','hermes']:
   profile=next(x for x in profiles if x['unit']==u and x['family']==family);root=R/'runs-reuse'/f'u{u}'/family;ledger=receipts[str(root.relative_to(R))];resource=json.loads((root/'profile-resources.json').read_text());valid=profile['valid_new_deliveries']
   values[family]=dict(fee=ledger['observed_fee']/valid if valid else None,ram=resource['peak_memory_bytes']/1048576,cpu=resource['cpu']['usage_usec']/1000000/valid if valid else None,complete=not ledger['incomplete'],quality=len(profile['episodes'])==3 and all(x['passed'] for x in profile['episodes']) and valid==2)
   descriptive.append(dict(unit=u,family=family,task=profile['task'],training_fee=profile['training_cost'],all_profile_fee=ledger['observed_fee'],new_valid_deliveries=valid,amortized_fee=values[family]['fee'],profile_peak_MiB=values[family]['ram'],all_profile_cpu_seconds=resource['cpu']['usage_usec']/1000000,amortized_cpu_seconds=values[family]['cpu'],quality=values[family]['quality'],billing_complete=values[family]['complete'],scope='Training is not a new business delivery. Full peak memory is not divided by delivery count. Entire profile ledger including auxiliary calls is authoritative.'))
  common=dict(unit=f'learned-profile-u{u}',cluster=f'learned-profile-u{u}',case='learned_workloads')
  for dest,key in [(fee,'fee'),(ram,'ram'),(cpu,'cpu')]:
   if values['openclaw'][key] is not None and values['hermes'][key] is not None:dest.append(dict(**common,oc=values['openclaw'][key],hermes=values['hermes'][key]))
 evidence=['results/current-comparison.json','results/formal-integrity-audit.json','results/usage-reconciliation.json','results/reuse.json','results/additional-usage-reconciliation.json','results/reuse-efficiency-ledger.json','evidence/resource-selftest.json']
 save(R/'results/reuse-efficiency-ledger.json',descriptive)
 for name,pairs in [('D05a',fee),('D05b',ram),('D05c',cpu)]:obs['metrics'][name]=dict(pairs=pairs,evidence=evidence,scope='Frozen equal mix: W1/W2/W3/W4/learned each20%, six paired observations per class. Formal repeats cluster by task variant; learning clusters by independent profile. Native background/auxiliary/training/retries retained. Explicitly local authorized execution profile, not best Docker security mode.')
 valid_resource=load('formal-integrity-audit')['audit_passed'] and json.loads((R/'evidence/resource-selftest.json').read_text())['passed'];valid_fee=all(not x['cost_incomplete'] for x in formal['cases']) and all(x['billing_complete'] for x in descriptive);quality=all(x['passed'] for x in formal['cases']) and all(x['quality'] for x in descriptive)
 obs.setdefault('validity',{})['D05']={'资源采集必须通过父子进程已知负载自检':dict(status='pass' if valid_resource else 'fail',evidence=evidence),'失败与重试费用必须计入':dict(status='pass' if valid_fee else 'fail',evidence=evidence)}
 obs.setdefault('eligibility',{})['D05']={'有效交付范围与质量必须满足冻结的共同验收门槛':dict(status='pass' if quality else 'fail',evidence=evidence)}
 save(R/'results/observations.json',obs)
 from assemble_observations import main as refresh
 refresh();protocol=json.loads((D/'protocol_v1.json').read_text());obs=load('observations');save(R/'results/weight-sensitivity.json',{p:score(protocol,obs,p) for p in protocol['sensitivity_profiles']})
 print('D05_MIX_COMPLETE',len(fee),len(ram),len(cpu))
if __name__=='__main__':main()
