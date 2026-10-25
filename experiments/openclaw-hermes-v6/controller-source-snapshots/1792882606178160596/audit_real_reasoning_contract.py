"""Successful real common-model runs that actually received nonempty reasoning.
This is not a guarantee about other vendors' opaque thinking/signature formats.
"""
import hashlib,json,re
from pathlib import Path
from runtime import R,save

def main():
 cases=json.loads((R/'results/current-comparison.json').read_text())['cases'];rows=[]
 for family in ['openclaw','hermes']:
  for unit in range(1,4):
   case=next(x for x in cases if x['family']==family and x['task']=='W1' and x['variant']==unit and x['repeat']==1);root=Path(case['evidence']);root=root if root.is_absolute() else R/root;found=[]
   for request in sorted(root.glob('api-request-*.json')):
    body=json.loads(request.read_text())
    if not body.get('tools'):continue
    raw=root/request.name.replace('api-request-','api-response-').replace('.json','.raw')
    if not raw.exists():continue
    data=raw.read_bytes()
    if re.search(rb'"reasoning_content"\s*:\s*"[^"\s]',data):
     found.append(dict(request=str(request.relative_to(R)),response=str(raw.relative_to(R)),raw_sha256=hashlib.sha256(data).hexdigest()));break
   rows.append(dict(unit=unit,family=family,task_passed_independent_acceptance=case['passed'],nonempty_reasoning_received=bool(found),evidence=found,scope='Actual DeepSeek Flash high Chat response plus independently accepted complete task. Positive parsing/tool-loop contract only; no vendor opaque-signature replay or true context-capacity certification.'))
 save(R/'results/real-reasoning-contract-audit.json',rows);print('REAL_REASONING_CONTRACT',sum(x['nonempty_reasoning_received'] and x['task_passed_independent_acceptance'] for x in rows),len(rows))
if __name__=='__main__':main()
