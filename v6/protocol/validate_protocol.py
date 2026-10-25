import json
from pathlib import Path
R=Path(__file__).resolve().parent;p=json.loads((R/'protocol_v1.json').read_text())
assert len(p['dimensions'])==11
ids={x['id'] for x in p['experiments']};assert len(ids)==14
for d in p['dimensions']:
 assert sum(c['weight'] for c in d['criteria'])==100
 assert (d['critical_gates'] or d['validity_gates'] or d['eligibility_gates']) and d['architectural_question']
 assert all(set(c['experiments'])<=ids for c in d['criteria'])
assert len(p['faults'])==10 and len(p['security_probes'])==16 and len(p['control_cases'])==12
assert len(p['workloads'])==4 and len(p['ablations'])==6
from score_protocol import selftest,score
r=selftest()
o=json.loads((R/'observations_template.json').read_text());o['preflight_valid']=True
empty=score(p,o);assert all(all(v is None for v in d['grades'].values()) for d in empty['dimensions'])
import copy
guards=1
for field,value in [('protocol_semantic_sha256','wrong'),('peer_set',['five-products-not-measured']),('preflight_valid',False),('protocol_version','stale')]:
 q=copy.deepcopy(o);q[field]=value
 try:score(p,q)
 except ValueError:guards+=1
 else:raise AssertionError(field+' not guarded')
for profile,want in [('api_cost_priority',[70,20,10]),('memory_priority',[20,70,10])]:
 z=score(p,o,profile);d=next(x for x in z['dimensions'] if x['id']=='D05')
 assert [x['weight'] for x in d['criteria']]==want and not z['primary_result'];guards+=1
(R/'protocol_validation.json').write_text(json.dumps({'protocol_integrity':True,'dimensions':11,'experiments':14,'score_selftests':r,'global_guard_tests':guards,'formal_execution_started':False},indent=2))
print('Validated 11 dimensions, weights=100 each, all references, case matrices,',r['checks'],'scoring edge cases and',guards,'global guards.')
