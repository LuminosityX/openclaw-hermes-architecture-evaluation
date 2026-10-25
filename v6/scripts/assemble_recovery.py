"""Frozen D01 acceptance; manual recovery is not rewritten as automatic survival."""
import json
from runtime import R,save

def load(n):return json.loads((R/'results'/(n+'.json')).read_text())
def find(rows,u,f,kind=None):
 v=[r for r in rows if r.get('unit',r.get('independent_unit'))==u and r['family']==f and (kind is None or r.get('kind')==kind)]
 if len(v)!=1:raise RuntimeError('Missing/ambiguous native unit '+str((u,f,kind)))
 return v[0]
def main():
 if not (R/'results/plugin-standard-resume.json').exists():print('D01_WAITING_ORIGINAL_R09_RESUME');return
 n=load('native-suite');c=load('control-faults');a=load('native-async-recovery');child=load('child-standard-resume');plugin=load('gateway-plugin-fault');follow=load('plugin-standard-resume');storage=load('native-storage-faults');pairs_a=[];pairs_b=[]
 if len(follow)!=3 or len(storage)!=6:raise RuntimeError('Recovery units incomplete')
 for u in range(1,4):
  for case in ['R01','R02','R03','R04','R06','R07','R08','R09']:
   values={}
   for f in ['openclaw','hermes']:
    if case in ['R01','R02']:
     row=find(n,u,f,'retry-'+('429' if case=='R01' else '503')+'-r1');value=row['exit_code']==0 and row['main_provider_requests']>=1
    elif case=='R03':value=find(c,u,f,'R03-truncated-stream')['recovered']
    elif case=='R04':value=find(c,u,f,'R04-tool-before-effect')['completed']
    elif case in ['R06','R07']:value=find(a,u,f,case)['finished_after_intervention']
    elif case=='R08':value=find(child,u,f)['completed_after_standard_resume']
    elif f=='hermes':value=find(plugin,u,f)['same_task_continued']
    else:value=find(follow,u,f)['same_original_conversation_continued']
    values[f]=bool(value)
   pairs_a.append(dict(unit=f'{case}-u{u}',case=case,oc=values['openclaw'],hermes=values['hermes']))
  for case in ['R05','R07','R08','R10']:
   values={}
   for f in ['openclaw','hermes']:
    if case=='R05':
     row=find(c,u,f,'R05-lost-commit-ack');value=row['safe_reconciliation'] and row['effect_count']==1
    elif case=='R07':
     row=find(a,u,f,'R07');value=row['native_persisted_before_fault'] and row['finished_after_intervention'] and row['effect_count']==1
    elif case=='R08':
     row=find(child,u,f);value=row['child_result_durable_before_fault'] and row['child_result_retained_after_restart'] and row['completed_after_standard_resume'] and row['child_execution_count']==1
    else:
     row=find(storage,u,f);ack=row['during']['response'].get('acknowledged')
     if f=='openclaw':
      raw=json.loads((R/'runs-storage-faults/native-EIO'/f'u{u}'/f/'native-eio-fault-admission.json').read_text());ack=False if raw.get('ok') is False else ack
     value=row['valid_fault'] and ack is False and row['after_persisted'] and row['preexisting_state_retained']
    values[f]=bool(value)
   pairs_b.append(dict(unit=f'{case}-u{u}',case=case,oc=values['openclaw'],hermes=values['hermes']))
 obs=load('observations');evidence=['results/native-suite.json','results/control-faults.json','results/native-async-recovery.json','results/child-standard-resume.json','results/gateway-plugin-fault.json','results/plugin-standard-resume.json','results/native-storage-faults.json']
 obs['metrics']['D01a']=dict(pairs=pairs_a,evidence=evidence,scope='Correct eventual completion is distinct from automatic wake-up and uninterrupted service. R09 followup belongs to the original three fault units, not additional samples. Both manual and automatic paths are visible in native raw records.')
 obs['metrics']['D01b']=dict(pairs=pairs_b,evidence=evidence,scope='Fixed model plan queries the application receipt after lost ACK. No generic exactly-once or autonomous reasoning guarantee. Native EIO errors were explicit rejections; OpenClaw acknowledged=null in controller summary is reconciled by the saved native ok=false response, never converted to admitted work.')
 # R09 followup is a later same-unit snapshot; its observation does not establish
 # complete fault-to-ready intervention timing. Do not manufacture D01c parity.
 obs.setdefault('criterion_limits',{})['D01c']='Mixed automatic/explicit confirmation/re-attachment and R09 followup timing are reported individually; whole frozen intervention-time contract is not established. Weight20 remains unknown.'
 ok=all(x['oc'] and x['hermes'] for x in pairs_a+pairs_b)
 gates=['不得伪造完成','不得静默丢失已承诺持久接收的工作','不确定副作用不得盲重放造成重复']
 obs.setdefault('gates',{})['D01']={g:dict(oc='pass' if ok else 'fail',hermes='pass' if ok else 'fail',evidence=evidence) for g in gates}
 if not ok:raise RuntimeError('Inspect specific failed recovery assertion before assigning product gate failure')
 save(R/'results/observations.json',obs)
 from assemble_observations import main as refresh
 refresh()
if __name__=='__main__':main()
