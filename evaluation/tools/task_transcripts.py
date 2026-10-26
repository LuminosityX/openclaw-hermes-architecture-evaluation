"""Golden local transcripts for wiring calibration, never task-quality evidence."""
import io
import json


MONEY_CODE='''from decimal import Decimal, ROUND_HALF_UP
def reconcile(rows):
    totals = {}
    for row in rows:
        if row['status'] == 'cancelled':
            continue
        value = Decimal(row['amount'])
        if row['kind'] == 'refund':
            value = -value
        key = row['currency']
        totals[key] = totals.get(key, Decimal(0)) + value
    return {key: str(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)) for key, value in sorted(totals.items())}
'''

GRAPH_CODE='''import heapq
def dependency_order(graph):
    nodes = set(graph)
    for prerequisites in graph.values():
        nodes.update(prerequisites)
    remaining = {node: set(graph.get(node, [])) for node in nodes}
    ready = [node for node in nodes if not remaining[node]]
    heapq.heapify(ready)
    result = []
    while ready:
        node = heapq.heappop(ready)
        result.append(node)
        for dependent in sorted(nodes):
            if node in remaining[dependent]:
                remaining[dependent].remove(node)
                if not remaining[dependent]:
                    heapq.heappush(ready, dependent)
    if len(result) != len(nodes):
        raise ValueError('cycle')
    return result
'''


class Response(io.BytesIO):
    status=200
    headers={}


def provider_for(task):
    """No network is accessed. Correct artifacts intentionally calibrate the oracle."""
    sid=task['scenario_id']
    if sid in {'PERF-09-S01','PERF-09-S02'}:
        code=MONEY_CODE if sid.endswith('01') else GRAPH_CODE
        operations=[('task_files',dict(op='write',path='solution.py',content=code)),('task_files',dict(op='test'))]
    elif sid in {'PERF-09-S03','PERF-09-S04'}:
        operations=[('task_files',dict(op='write',path=task['artifact'],content=json.dumps(task['oracle']['expected'])))]
    else:
        order=task['oracle']['order_id'];amount=task['oracle']['amount_cents']
        operations=[('task_service',dict(action='prepare',order_id=order,amount_cents=amount)),
                    ('task_service',dict(action='commit',order_id=order,idempotency_key='golden-stable-key')),
                    ('task_service',dict(action='status',order_id=order)),
                    ('task_files',dict(op='write',path='receipt.json',content=json.dumps(dict(order_id=order,amount_cents=amount,receipt_id='receipt-1'))))]
    attempt=0
    def open_request(request,timeout):
        nonlocal attempt
        body=json.loads(request.data)
        operation=operations[attempt] if attempt<len(operations) else None
        attempt+=1
        if operation:
            name,arguments=operation
            delta=dict(role='assistant',tool_calls=[dict(index=0,id='golden_call_'+str(attempt),type='function',function=dict(name=name,arguments=json.dumps(arguments)))])
            finish='tool_calls'
        else:
            delta=dict(role='assistant',content='Golden local transcript complete. This is fixture calibration only.')
            finish='stop'
        common=dict(id='golden-'+str(attempt),model='deepseek-flash',object='chat.completion.chunk')
        frames=[dict(**common,choices=[dict(index=0,delta=delta,finish_reason=None)]),
                dict(**common,choices=[dict(index=0,delta={},finish_reason=finish)]),
                dict(**common,choices=[],usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0))]
        payload=''.join('data: '+json.dumps(frame)+'\n\n' for frame in frames)+'data: [DONE]\n\n'
        return Response(payload.encode())
    return open_request
