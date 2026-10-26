"""Versioned task inputs and independent acceptance for all five PERF-09 task types.

Acceptance data stays on the hosted controller, outside agent-visible tool files.
Native execution adapters must supply artifacts and service receipts; these
fixtures alone are not OpenClaw results.
"""
import csv
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import heapq
import io
import json
import random

TASK_SCHEMA=1


def text_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def public_test(function,arguments,expected):
    return ('import json\nfrom solution import '+function+'\n'
            'actual='+function+'('+repr(arguments)+')\n'
            'assert actual == '+repr(expected)+', repr(actual)\n'
            'print("PUBLIC_TEST_PASSED")\n')


def money_result(rows):
    totals={}
    for row in rows:
        if row['status']=='cancelled': continue
        value=Decimal(row['amount'])
        if row['kind']=='refund': value=-value
        totals[row['currency']]=totals.get(row['currency'],Decimal(0))+value
    return {currency:str(total.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)) for currency,total in sorted(totals.items())}


def dependency_result(graph):
    nodes=set(graph)|{d for deps in graph.values() for d in deps}
    remaining={node:set(graph.get(node,[])) for node in nodes}
    available=[node for node in nodes if not remaining[node]]
    heapq.heapify(available)
    emitted=[]
    while available:
        node=heapq.heappop(available)
        emitted.append(node)
        for dependent in sorted(remaining):
            if node in remaining[dependent]:
                remaining[dependent].remove(node)
                if not remaining[dependent]: heapq.heappush(available,dependent)
    if len(emitted)!=len(nodes): return {'error':'ValueError'}
    return emitted


def csv_text(rows):
    output=io.StringIO()
    writer=csv.DictWriter(output,fieldnames=['id','revision','group','amount','deleted'],lineterminator='\n')
    writer.writeheader();writer.writerows(rows)
    return output.getvalue()


def reconciliation_result(sources):
    winners={}
    for source_index,rows in enumerate(sources):
        for row_index,row in enumerate(rows):
            priority=(int(row['revision']),source_index,row_index)
            if row['id'] not in winners or priority>winners[row['id']][0]: winners[row['id']]=(priority,row)
    records=[row for _,row in winners.values() if row['deleted']=='false']
    totals={}
    for row in records: totals[row['group']]=totals.get(row['group'],Decimal(0))+Decimal(row['amount'])
    return dict(active_ids=sorted(row['id'] for row in records),
                totals={key:str(value.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)) for key,value in sorted(totals.items())})


def workload(scenario_id,unit):
    if scenario_id not in {f'PERF-09-S{i:02}' for i in range(1,6)}: raise ValueError('Unknown independent task type')
    if type(unit) is not int or not 1<=unit<=6: raise ValueError('Task unit must be 1..6')
    rng=random.Random(9000+100*int(scenario_id[-2:])+unit)
    files={}
    task=dict(schema_version=TASK_SCHEMA,scenario_id=scenario_id,unit=unit,
              task_id='EVAL_'+scenario_id.replace('-','_')+'_U'+str(unit),
              model='deepseek-flash',provider='deepseek',files=files,
              timeout_seconds=180,maximum_model_requests=16,maximum_output_tokens_per_request=4096)
    if scenario_id=='PERF-09-S01':
        task['prompt']='Repair solution.py. reconcile(rows) must ignore cancelled rows, subtract refunds, aggregate exact decimal amounts per currency, and return a currency-sorted dict of two-decimal strings rounded HALF_UP once at the end. Empty input returns {}. Preserve the function name. Run the public tests, then deliver solution.py.'
        files['solution.py']='def reconcile(rows):\n    total = sum(float(r["amount"]) for r in rows)\n    return {"USD": str(total)}\n'
        sample=[dict(amount='0.10',currency='USD',kind='charge',status='active'),dict(amount='0.20',currency='USD',kind='charge',status='active')]
        files['public_tests.py']=public_test('reconcile',sample,{'USD':'0.30'})
        inputs=[[],sample]
        for _ in range(8):
            inputs.append([dict(amount=f'{rng.randrange(2000)/100:.2f}',currency=rng.choice(['USD','EUR','CNY']),
                                kind=rng.choice(['charge','refund']),status=rng.choice(['active','active','cancelled'])) for _ in range(rng.randrange(1,20))])
        task.update(artifact='solution.py',oracle=dict(kind='python-function',function='reconcile',inputs=inputs,expected=[money_result(rows) for rows in inputs]))
    elif scenario_id=='PERF-09-S02':
        task['prompt']='Implement dependency_order(graph) in solution.py. graph maps string node names to their prerequisite names. Include referenced-only nodes, deduplicate dependencies, and repeatedly choose the lexicographically smallest currently available node. Return the ordered node list. Raise ValueError on a cycle. Empty input returns []. Run the public tests and deliver solution.py.'
        files['solution.py']='def dependency_order(graph):\n    raise NotImplementedError\n'
        files['public_tests.py']=public_test('dependency_order',{'b':['a'],'c':[]},['a','b','c'])
        inputs=[{}, {'b':['a','a'],'c':[]}, {'x':['y'],'y':['x']}, {'self':['self']}]
        for _ in range(8):
            labels=[f'n{i}' for i in range(rng.randrange(3,10))]
            graph={node:[prior for prior in labels[:index] if rng.randrange(3)==0] for index,node in enumerate(labels)}
            graph[labels[-1]].append('referenced-only')
            inputs.append(graph)
        task.update(artifact='solution.py',oracle=dict(kind='python-function',function='dependency_order',inputs=inputs,expected=[dependency_result(graph) for graph in inputs]))
    elif scenario_id=='PERF-09-S03':
        task['prompt']='Reconcile input-a.csv and input-b.csv. Per id, select the row with greatest integer revision; ties prefer input-b, then the later row in that file. Remove rows whose deleted field is true. Write result.json with exactly active_ids (sorted strings) and totals (group -> exact two-decimal sum strings, HALF_UP rounded at the end). Include groups whose active rows sum to zero. Do not modify inputs.'
        sources=[]
        for source in range(2):
            rows=[dict(id=f'item-{i}',revision=str(rng.randrange(1,5)),group=rng.choice(['alpha','beta','gamma']),
                       amount=f'{rng.randrange(-20000,20000)/100:.2f}',deleted='true' if (i+source+unit)%7==0 else 'false') for i in range(24)]
            rows.append(dict(rows[3],amount='0.10'))
            sources.append(rows)
        files['input-a.csv']=csv_text(sources[0]);files['input-b.csv']=csv_text(sources[1])
        task.update(artifact='result.json',oracle=dict(kind='json-artifact',expected=reconciliation_result(sources)))
    elif scenario_id=='PERF-09-S04':
        ttl=11+unit;retention=2+unit
        files['docs-2025.txt']='L1: release=2025-12\nL2: cache TTL is 7 seconds.\nL3: legacy export is enabled.\nL4: retention is 30 days.\n'
        files['docs-current.txt']=f'L1: release=2026-10\nL2: cache TTL is {ttl} seconds.\nL3: legacy export is disabled.\nL4: retention is {retention} days.\n'
        files['docs-draft.txt']='L1: status=draft; not released\nL2: proposal: cache TTL 999 seconds.\nL3: proposal: unlimited retention.\n'
        task['prompt']='Using only the supplied documents, report the latest released settings. Ignore unreleased drafts. Write answer.json with cache_ttl_seconds, legacy_export_enabled, retention_days and citations. citations must map each of those three keys to an exact source reference in the form filename:L<number>. Keep numeric values as JSON numbers and enabled as a JSON boolean.'
        expected=dict(cache_ttl_seconds=ttl,legacy_export_enabled=False,retention_days=retention,
            citations=dict(cache_ttl_seconds='docs-current.txt:L2',legacy_export_enabled='docs-current.txt:L3',retention_days='docs-current.txt:L4'))
        task.update(artifact='answer.json',oracle=dict(kind='json-artifact',expected=expected))
    else:
        order_id='order-'+str(unit)
        amount_cents=1200+unit*17
        files['order.json']=json.dumps(dict(order_id=order_id,amount_cents=amount_cents))+'\n'
        task['prompt']='Complete the order in order.json using task_service. Supported actions are prepare, commit, and status. prepare requires order_id and amount_cents. commit requires order_id and a stable idempotency_key of your choosing. status requires order_id and returns any committed receipt. Network acknowledgments can be lost: recover without creating duplicate effects. Write receipt.json containing exactly order_id, amount_cents and receipt_id from the actual service receipt. Finish only after independently checking status.'
        task.update(artifact='receipt.json',oracle=dict(kind='service-receipt',order_id=order_id,amount_cents=amount_cents),
                    service_fixture=dict(order_id=order_id,amount_cents=amount_cents,lose_first_commit_ack=True))
    public=dict(task_id=task['task_id'],prompt=task['prompt'],files=dict(files),artifact=task['artifact'],
                resource_limits={k:task[k] for k in ['timeout_seconds','maximum_model_requests','maximum_output_tokens_per_request']})
    task['public']=public
    task['public_fixture_sha256']=text_hash(json.dumps(public,sort_keys=True,ensure_ascii=False,separators=(',',':')))
    return task


def judge(task,artifacts,function_results=None,service_events=None):
    """Judge controller-owned oracle data against actual artifacts/receipts."""
    oracle=task['oracle']
    assertions=[]
    def check(name,value): assertions.append(dict(name=name,verdict='pass' if value else 'fail',evidence=['task-artifact','independent-task-oracle']))
    content=artifacts.get(task['artifact'])
    check('required-artifact-delivered',isinstance(content,str) and bool(content.strip()))
    if oracle['kind']=='python-function':
        check('independent-functional-cases',function_results==oracle['expected'])
        check('all-functional-cases-accounted',isinstance(function_results,list) and len(function_results)==len(oracle['inputs']))
    else:
        try: actual=json.loads(content or '')
        except (ValueError,TypeError): actual=None
        if oracle['kind']=='json-artifact': check('independent-exact-deliverable',actual==oracle['expected'])
        else:
            events=service_events or []
            commits=[e for e in events if e.get('kind')=='commit-effect']
            statuses=[e for e in events if e.get('kind')=='status-read']
            check('exactly-one-external-effect',len(commits)==1)
            check('status-verified-after-commit',bool(commits and statuses) and statuses[-1]['sequence']>commits[0]['sequence'])
            expected=None if not commits else {k:commits[0].get(k) for k in ['order_id','amount_cents','receipt_id']}
            check('deliverable-matches-independent-receipt',actual==expected and expected is not None)
            check('correct-order-and-amount',bool(commits) and commits[0].get('order_id')==oracle['order_id'] and commits[0].get('amount_cents')==oracle['amount_cents'])
    return dict(accepted=all(a['verdict']=='pass' for a in assertions),assertions=assertions,
                public_fixture_sha256=task['public_fixture_sha256'],schema_version=TASK_SCHEMA)
