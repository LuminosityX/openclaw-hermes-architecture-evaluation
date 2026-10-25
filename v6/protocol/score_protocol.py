"""Deterministic two-product grading from preregistered observations.

No model-generated scores are accepted. Every metric supplies measured pairs and evidence.
The architecture explanation is a separate reviewed report field.
"""
import argparse,copy,hashlib,json,math,random,statistics
from pathlib import Path
R=Path(__file__).resolve().parent

def quant_compare(metric,margin,expected_cases=()):
    pairs=[x for x in metric.get('pairs',[]) if x.get('valid',True)]
    if expected_cases and not set(expected_cases)<={x.get('case') for x in pairs}:return {'outcome':None,'why':'required_case_class_missing'}
    if expected_cases and any(len({x['unit'] for x in pairs if x.get('case')==c})<6 for c in expected_cases):return {'outcome':None,'why':'each_preregistered_case_class_requires_6_paired_units'}
    if len({x['unit'] for x in pairs})<6:return {'outcome':None,'why':'fewer_than_6_independent_paired_units'}
    if len(pairs)!=len({x['unit'] for x in pairs}):raise ValueError('Aggregate repeated batches within each unit before quantitative comparison')
    if not all(type(x.get('oc')) in (int,float) and type(x.get('hermes')) in (int,float) and math.isfinite(x['oc']) and math.isfinite(x['hermes']) and x['oc']>0 and x['hermes']>0 for x in pairs):
        raise ValueError('Quantitative measurements must be positive; do not invent epsilon for zero')
    sign=1 if metric.get('lower_is_better',True) else -1
    groups={}
    for x in pairs:groups.setdefault(x.get('cluster',x['unit']),[]).append(sign*math.log(x['oc']/x['hermes']))
    if len(groups)<6:return {'outcome':None,'why':'fewer_than_6_independent_clusters'}
    names=sorted(groups);rng=random.Random(20261024);samples=[]
    for _ in range(2000):
        values=[]
        for name in rng.choices(names,k=len(names)):
            values.extend(rng.choices(groups[name],k=len(groups[name])))
        samples.append(math.exp(statistics.mean(values)))
    samples.sort();ci=[samples[49],samples[1949]]
    ratio=math.exp(statistics.mean(sign*math.log(x['oc']/x['hermes']) for x in pairs))
    bound=1+margin
    if ratio<=1/bound and ci[1]<1:outcome=1;why='oc_material_advantage_with_interval_excluding_parity'
    elif ratio>=bound and ci[0]>1:outcome=-1;why='hermes_material_advantage_with_interval_excluding_parity'
    elif ci[0]>=1/bound and ci[1]<=bound:outcome=0;why='interval_inside_preregistered_equivalence_band'
    else:outcome=None;why='measured_but_not_yet_distinguishable'
    return dict(outcome=outcome,why=why,ratio_oc_over_hermes_effective_lower_better=ratio,paired_interval95=ci,n_units=len({x['unit'] for x in pairs}),n_clusters=len(groups),material_ratio=bound)

def functional_compare(metric,expected_cases=()):
    pairs=[x for x in metric.get('pairs',[]) if x.get('valid',True)]
    if len({x['unit'] for x in pairs})<3:return {'outcome':None,'why':'fewer_than_3_independent_functional_units'}
    if not all(type(x.get('oc')) is bool and type(x.get('hermes')) is bool for x in pairs):
        raise ValueError('Functional observations require actual boolean acceptance, not absent/unsupported environment guesses')
    grouped={}
    for x in pairs:grouped.setdefault(x.get('case','default'),[]).append(x)
    if expected_cases and not set(expected_cases)<=set(grouped):return {'outcome':None,'why':'required_case_class_missing'}
    if any(len({x['unit'] for x in rs})<3 for rs in grouped.values()):return {'outcome':None,'why':'each_case_requires_3_fresh_units'}
    if any(len({(x['oc'],x['hermes']) for x in rs})!=1 for rs in grouped.values()):return {'outcome':None,'why':'functional_result_not_reproduced_consistently'}
    delta=statistics.mean(rs[0]['oc']-rs[0]['hermes'] for rs in grouped.values())
    if delta>=.20:return dict(outcome=1,why='reproduced_functional_gap',acceptance_rate_difference=delta)
    if delta<=-.20:return dict(outcome=-1,why='reproduced_functional_gap',acceptance_rate_difference=delta)
    return dict(outcome=0,why='same_acceptance_or_verified_tradeoff_on_frozen_cases',acceptance_rate_difference=delta)

def ordinal_compare(metric,expected_cases=()):
    pairs=[x for x in metric.get('pairs',[]) if x.get('valid',True)]
    if len({x['unit'] for x in pairs})<3:return {'outcome':None,'why':'fewer_than_3_matched_extension_or_operations_cases'}
    if expected_cases and not set(expected_cases)<={x.get('case') for x in pairs}:return {'outcome':None,'why':'required_case_class_missing'}
    if not all(x.get('reviewed') is True and x.get('evidence') for x in pairs):return {'outcome':None,'why':'implementation_route_needs_evidence_and_review'}
    delta=[x['oc']-x['hermes'] for x in pairs]
    if all(x==0 for x in delta):return {'outcome':0,'why':'same_reviewed_route_class'}
    if all(x<=0 for x in delta) and sum(x<0 for x in delta)>=2:return {'outcome':1,'why':'oc_more_local_supported_route_on_matched_cases'}
    if all(x>=0 for x in delta) and sum(x>0 for x in delta)>=2:return {'outcome':-1,'why':'hermes_more_local_supported_route_on_matched_cases'}
    return {'outcome':None,'why':'route_tradeoff_needs_subcriterion_split_or_review'}

def grade_dimension(d,observations):
    metrics=observations.get('metrics',{});gate_data=observations.get('gates',{}).get(d['id'],{})
    compared=[];lo=hi=known=measured=0
    for c in d['criteria']:
        m=metrics.get(c['id'])
        if m is None:result={'outcome':None,'why':'not_measured'}
        elif not m.get('evidence'):result={'outcome':None,'why':'missing_evidence_reference'}
        else:
            if any(x.get('valid',True) for x in m.get('pairs',[])):measured+=c['weight']
            if c['kind']=='quantitative':result=quant_compare(m,c['material_margin'],c.get('expected_cases',()))
            elif c['kind']=='ordinal':result=ordinal_compare(m,c.get('expected_cases',()))
            else:result=functional_compare(m,c.get('expected_cases',()))
        result.update(id=c['id'],label=c['label'],weight=c['weight']);compared.append(result)
        if result['outcome'] is None:lo-=c['weight'];hi+=c['weight']
        else:lo+=c['weight']*result['outcome'];hi+=c['weight']*result['outcome'];known+=c['weight']
    grades={'openclaw':None,'hermes':None};status='not_final';confidence='insufficient'
    # These gates assess the experiment/quantity comparison, never the product grade.
    validity=observations.get('validity',{}).get(d['id'],{})
    eligibility=observations.get('eligibility',{}).get(d['id'],{})
    invalid=[name for name in d.get('validity_gates',[]) if not validity.get(name,{}).get('evidence') or validity[name].get('status')!='pass']
    ineligible=[name for name in d.get('eligibility_gates',[]) if not eligibility.get(name,{}).get('evidence') or eligibility[name].get('status')!='pass']
    gates=[gate_data.get(name) for name in d['critical_gates']]
    gates_complete=all(g and g.get('evidence') and g.get('oc') in ['pass','fail'] and g.get('hermes') in ['pass','fail'] for g in gates)
    if invalid:reason='experiment_validity_not_established'
    elif ineligible:reason='comparison_eligibility_not_established'
    elif not gates_complete:reason='critical_gate_evidence_incomplete'
    else:
        oc_bad=any(g['oc']=='fail' for g in gates);h_bad=any(g['hermes']=='fail' for g in gates)
        if oc_bad or h_bad:
            grades={'openclaw':'弱' if oc_bad else '强','hermes':'弱' if h_bad else '强'};status='critical_gate_decision';reason='verified_critical_failure';confidence='mechanism_scope_only'
        elif known<80:reason='distinguishable_weight_below_80'
        elif lo>=25:grades={'openclaw':'强','hermes':'弱'};status='graded';reason='robust_weighted_advantage';confidence='high' if known==100 else 'bounded'
        elif hi<=-25:grades={'openclaw':'弱','hermes':'强'};status='graded';reason='robust_weighted_advantage';confidence='high' if known==100 else 'bounded'
        elif lo>-25 and hi<25:grades={'openclaw':'中','hermes':'中'};status='graded';reason='verified_parity_or_weighted_tradeoff';confidence='high' if known==100 else 'bounded'
        else:reason='advantage_interval_crosses_grade_boundary'
    return dict(dimension=d['name'],id=d['id'],grades=grades,status=status,reason=reason,confidence=confidence,measured_weight=measured,distinguishable_weight=known,advantage_interval=[lo,hi],criteria=compared,gates_complete=gates_complete,validity_missing_or_failed=invalid,eligibility_missing_or_failed=ineligible)

def score(protocol,observations,profile='default'):
    if observations.get('peer_set')!=protocol['peer_set']:raise ValueError('Peer set mismatch; two-product results cannot masquerade as five-product normalization')
    if observations.get('protocol_version')!=protocol['version']:raise ValueError('Protocol version mismatch')
    actual_scorer=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if protocol.get('scorer_sha256')!=actual_scorer:raise ValueError('Scorer source differs from the protocol lock')
    digest=hashlib.sha256(json.dumps(protocol,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if observations.get('protocol_semantic_sha256')!=digest:raise ValueError('Protocol content hash mismatch; criteria cannot silently change after observations')
    if observations.get('preflight_valid') is not True:raise ValueError('Valid effective configuration and measurement preflight required')
    if profile not in protocol.get('sensitivity_profiles',{'default':{}}):raise ValueError('Unregistered sensitivity profile')
    overrides=protocol.get('sensitivity_profiles',{}).get(profile,{})
    results=[]
    for original in protocol['dimensions']:
        d=copy.deepcopy(original)
        if d['id'] in overrides:
            for c in d['criteria']:c['weight']=overrides[d['id']][c['id']]
            if sum(c['weight'] for c in d['criteria'])!=100:raise ValueError('Profile weights must sum to100')
        try:results.append(grade_dimension(d,observations))
        except (ValueError,KeyError,TypeError) as error:results.append(dict(id=d['id'],dimension=d['name'],grades={'openclaw':None,'hermes':None},status='invalid_measurement_record',reason=str(error)))
    return {'protocol_version':protocol['version'],'protocol_semantic_sha256':digest,'peer_set':protocol['peer_set'],'relative_grading':True,'weight_profile':profile,'primary_result':profile=='default','dimensions':results}

def selftest():
    d=dict(id='T',name='synthetic_selftest',criteria=[dict(id='a',label='A',weight=40,kind='functional'),dict(id='b',label='B',weight=40,kind='functional'),dict(id='c',label='C',weight=20,kind='functional')],critical_gates=['gate'])
    def obs(outcomes):
        o={'metrics':{},'gates':{'T':{'gate':dict(oc='pass',hermes='pass',evidence='synthetic_positive_control')}}}
        for name,v in outcomes.items():
            if v is None:continue
            a,b=(True,False) if v==1 else (False,True) if v==-1 else (True,True)
            o['metrics'][name]=dict(evidence='synthetic_not_product_data',pairs=[dict(unit=str(i),case='same',oc=a,hermes=b) for i in range(3)])
        return o
    checks=[]
    r=grade_dimension(d,obs(dict(a=1,b=1,c=0)));checks.append(r['grades']=={'openclaw':'强','hermes':'弱'})
    r=grade_dimension(d,obs(dict(a=-1,b=-1,c=0)));checks.append(r['grades']=={'openclaw':'弱','hermes':'强'})
    r=grade_dimension(d,obs(dict(a=1,b=-1,c=0)));checks.append(r['grades']=={'openclaw':'中','hermes':'中'})
    r=grade_dimension(d,obs(dict(a=0,b=0,c=None)));checks.append(r['grades']=={'openclaw':'中','hermes':'中'} and r['advantage_interval']==[-20,20])
    r=grade_dimension(d,obs(dict(a=None,b=0,c=0)));checks.append(r['grades']=={'openclaw':None,'hermes':None})
    o=obs(dict(a=1,b=1,c=1));o['gates']={};checks.append(grade_dimension(d,o)['grades']['openclaw'] is None)
    o=obs(dict(a=0,b=0,c=0));o['gates']['T']['gate']['oc']='fail';checks.append(grade_dimension(d,o)['grades']=={'openclaw':'弱','hermes':'强'})
    q=dict(evidence='synthetic',pairs=[dict(unit=str(i),oc=1+i/100,hermes=4+i/100) for i in range(6)])
    checks.append(quant_compare(q,.2)['outcome']==1)
    q['pairs']=q['pairs'][:3];checks.append(quant_compare(q,.2)['outcome'] is None)
    q=dict(pairs=[dict(unit=str(i),cluster='only-one-service',oc=1,hermes=4) for i in range(6)])
    checks.append(quant_compare(q,.2)['outcome'] is None)
    q=dict(pairs=[dict(unit=str(i),oc=True,hermes=True) for i in range(3)])
    checks.append(functional_compare(q,['required-other-case'])['outcome'] is None)
    q=dict(pairs=[dict(unit=str(i),oc=float('inf'),hermes=1) for i in range(6)])
    try:quant_compare(q,.2)
    except ValueError:checks.append(True)
    else:checks.append(False)
    dd=dict(d,validity_gates=['meter_valid']);o=obs(dict(a=1,b=1,c=1));o['validity']={'T':{'meter_valid':{'status':'fail','evidence':'broken_meter'}}}
    checks.append(grade_dimension(dd,o)['grades']=={'openclaw':None,'hermes':None})
    dd=dict(d,eligibility_gates=['same_quality']);o=obs(dict(a=1,b=1,c=1));o['eligibility']={'T':{'same_quality':{'status':'fail','evidence':'quality_differs'}}}
    checks.append(grade_dimension(dd,o)['grades']=={'openclaw':None,'hermes':None})
    assert all(checks),checks
    return dict(passed=True,checks=len(checks),scope='Synthetic decision-rule selftests; these are not product grades')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--observations',type=Path);p.add_argument('--output',type=Path);p.add_argument('--selftest',action='store_true');p.add_argument('--profile',default='default');a=p.parse_args()
    if a.selftest:print(json.dumps(selftest(),ensure_ascii=False));raise SystemExit()
    if not a.observations:p.error('--observations is required')
    result=score(json.loads((R/'protocol_v1.json').read_text()),json.loads(a.observations.read_text()),a.profile)
    s=json.dumps(result,ensure_ascii=False,indent=2)
    if a.output:a.output.write_text(s)
    else:print(s)
