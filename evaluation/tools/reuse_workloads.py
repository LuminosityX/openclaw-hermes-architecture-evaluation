"""Paired real-provider cost sequences with a natively learned reusable asset."""
import hashlib
import json
import random


POLICIES={1:dict(base=7,multipliers=dict(local=1,regional=3,remote=5),vip_discount=2),
    2:dict(base=11,multipliers=dict(local=2,regional=4,remote=7),vip_discount=4)}


def answer(order,version):
    policy=POLICIES[version]
    return dict(order_id=order['order_id'],policy_version=version,
        credits=max(0,policy['base']+order['weight']*policy['multipliers'][order['zone']]-(policy['vip_discount'] if order['vip'] else 0)))


def workload(sid,unit):
    if sid not in {f'COST-03-S{i:02}' for i in range(1,5)} or type(unit) is not int or not 1<=unit<=6:raise ValueError('Unknown reuse sequence/unit')
    number=int(sid[-2:]);horizon={1:1,2:5,3:20,4:5}[number];task_id='EVAL_'+sid.replace('-','_')+'_U'+str(unit)
    rng=random.Random(31000+number*100+unit);orders=[];expected=[]
    for index in range(horizon):
        order=dict(order_id=f'order-{unit}-{index}',weight=rng.randrange(1,10),zone=rng.choice(['local','regional','remote']),vip=bool(rng.randrange(2)))
        version=2 if number==4 and index>=2 else 1;orders.append(dict(order=order,policy_version=version));expected.append(answer(order,version))
    files={}
    for version in ([1,2] if number==4 else [1]):
        files[f'rulebook-v{version}.txt']=('REUSABLE_POLICY_V'+str(version)+'\nPolicy parameters: '+json.dumps(POLICIES[version])+'\n'
            'Credits = max(0, base + weight * multipliers[zone] - (vip_discount if vip else 0)). All arithmetic is integer. '
            'Return order_id, policy_version and credits only.\n'+
            ''.join(f'Background policy note {i:03}: synthetic nonbinding service context; use the explicit parameters above.\n' for i in range(80)))
    learned='LEARNED_NATIVE_POLICY_V1\nUse only for current version 1. '+json.dumps(POLICIES[1])+'\nCredits=max(0,base+weight*multipliers[zone]-(vip_discount if vip else 0)). If the active version changes, read the matching current rulebook.\n'
    task=dict(schema_version=1,scenario_id=sid,unit=unit,task_id=task_id,provider='deepseek',model='deepseek-flash',
        files=files,artifact='series.json',prompt='Execute the registered paired reuse-cost sequence.',timeout_seconds=1150,whole_unit_timeout_seconds=1200,
        maximum_model_requests=128,maximum_output_tokens_per_request=4096,
        oracle=dict(kind='reuse-sequence',expected=expected),
        reuse=dict(horizon=horizon,orders=orders,arm_order=['baseline','reuse'] if unit%2 else ['reuse','baseline'],
            learning_prompt='Read rulebook-v1.txt and derive a concise reusable policy guide. Use the native write tool to save AGENTS.md in this workspace. Start it with LEARNED_NATIVE_POLICY_V1. Cover version 1 only, preserve the exact integer formula, and require consulting the matching rulebook when the active version changes. Do not change reference files or solve orders yet.',
            asset_marker='LEARNED_NATIVE_POLICY_V1',later_task_timeout_seconds=25,learning_timeout_seconds=60,
            golden_asset=learned))
    public=dict(task_id=task_id,prompt=task['prompt'],files=dict(files),artifact=task['artifact'],reuse={k:v for k,v in task['reuse'].items() if k!='golden_asset'},
        resource_limits={k:task[k] for k in ['timeout_seconds','maximum_model_requests','maximum_output_tokens_per_request']})
    task.update(public=public,public_fixture_sha256=hashlib.sha256(json.dumps(public,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
    return task


def judge(task,artifacts):
    from task_workloads import strict_equal
    try:series=json.loads(artifacts.get('series.json',''))
    except (ValueError,TypeError):series={}
    assertions=[]
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native/summary.json:artifacts.series.json','independent-policy-oracle']))
    accepted_deliveries={}
    for arm in ['baseline','reuse']:
        record=series.get(arm,{}) if isinstance(series,dict) else {};rows=record.get('answers',[])
        accepted=0
        for index,expected in enumerate(task['oracle']['expected']):
            row=rows[index] if index<len(rows) else {}
            try:value=json.loads(row.get('artifact_text') or '')
            except (ValueError,TypeError):value=None
            correct=strict_equal(value,expected) and row.get('status')==200 and type(row.get('latency_ms')) in {int,float} and row['latency_ms']<=task['reuse']['later_task_timeout_seconds']*1000
            accepted+=correct;check(arm+'-accepted-delivery-'+str(index),correct)
        check(arm+'-complete-registered-horizon',len(rows)==task['reuse']['horizon'])
        accepted_deliveries[arm]=accepted
    reuse=series.get('reuse',{}) if isinstance(series,dict) else {}
    check('native-learning-produced-the-registered-reusable-asset',reuse.get('asset_created') is True and reuse.get('asset_marker_present') is True)
    learning=reuse.get('learning',{})
    check('learning-call-completed-within-its-deadline',learning.get('status')==200 and type(learning.get('latency_ms')) in {int,float} and learning['latency_ms']<=task['reuse']['learning_timeout_seconds']*1000)
    return dict(accepted=all(a['verdict']=='pass' for a in assertions),assertions=assertions,
        public_fixture_sha256=task['public_fixture_sha256'],schema_version=1,accepted_deliveries=accepted_deliveries)
