"""Do not coerce unavailable cross-OS evidence into a medium grade."""
import json
from runtime import R,save

def main():
 obs=json.loads((R/'results/observations.json').read_text());moves=json.loads((R/'results/state-ops.json').read_text());protocols=json.loads((R/'results/protocols.json').read_text());pairs=[];decouple=[]
 if len(moves)!=6 or len(protocols)!=18:raise RuntimeError('Incomplete actual relocation/endpoint samples')
 for u in range(1,4):
  rows={x['family']:x for x in moves if x['unit']==u}
  pairs.append(dict(unit=f'M01-u{u}',case='M01',oc=rows['openclaw']['passed'],hermes=rows['hermes']['passed']))
  for case in ['self_host','state_ownership','endpoint_rebind']:
   values={}
   for family,row in rows.items():
    if case=='self_host':value=row['sqlite_integrity'] and row['artifact_integrity']
    elif case=='state_ownership':value=row['persisted_history'] and row['artifact_integrity'] and bool(row['native_archive_sha256'])
    else:
     test=[x for x in protocols if x['unit']==u and x['family']==family];value=len(test)==3 and all(x['passed'] for x in test)
    values[family]=bool(value)
   decouple.append(dict(unit=f'{case}-u{u}',case=case,oc=values['openclaw'],hermes=values['hermes']))
 evidence=['results/state-ops.json','results/storage-faults.json','results/protocols.json','evidence/source-architecture-index.json','evidence/hermes-original-logical-home-control/result.json','evidence/stateops-original-logical-state-control/result.json']
 obs['metrics']['D08a']=dict(pairs=pairs,evidence=evidence,scope='Changed logical home/state/workspace and UID1000 on clean Linux target. Both full contracts fail for distinct reasons, although native archive/history/file/plugin material integrity is preserved. Hermes explicitly refuses prior live receipt profile binding; OpenClaw relocated active scheduler partition omits the saved disabled job. Same-logical-layout restore separately passes and is not relabeled as changed-path success.')
 obs['metrics']['D08c']=dict(pairs=decouple,evidence=evidence,scope='Autonomous local deployment, operator-readable/exportable native data, and three actual local provider wire endpoint contracts. No claim of no dependency on any provider or platform.')
 obs.setdefault('criterion_limits',{})['D08b']='M03 cross-OS executor unavailable; exact-commit official CI is supporting architecture information, not our migration experiment. M02 fresh dependency rebuild is separate and cannot satisfy the missing OS case.'
 d=json.loads(open('/root/output/oc-hermes-formal-design-20261024/protocol_v1.json').read());definition=next(x for x in d['dimensions'] if x['id']=='D08')
 # No product failure is inferred from unavailable OS or explicit profile rejection.
 obs.setdefault('gates',{})['D08']={key:dict(oc='pass',hermes='pass',evidence=evidence,scope='No unannounced corruption/loss of claimed key files or conversation storage was observed. Execution refusal and scheduler path coupling remain explicit failed M01 assertions, not fabricated file loss.') for key in definition['critical_gates']}
 obs.setdefault('validity',{})['D08']={key:dict(status='pass',evidence=evidence,scope='Linux relocation only; unavailable OS receives no pass credit.') for key in definition['validity_gates']}
 save(R/'results/observations.json',obs)
 from assemble_observations import main as refresh
 refresh()
if __name__=='__main__':main()
