"""Reconstruct finite native events; never count fixture receipts as native audit.

This is a read-only evidence audit. Approval verdict association and the exact
authorization choice are deliberately separate: 'approved' does not say whether
the grant was once, session or always. Missing UUID alone does not fail a join.
"""
import ctypes
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from runtime import R, save

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()

def rows(db,table):
    c=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
    try:
        if not c.execute('select 1 from sqlite_master where type="table" and name=?',(table,)).fetchone():return []
        cur=c.execute('select * from "'+table.replace('"','""')+'"')
        names=[x[0] for x in cur.description]
        return [dict(zip(names,x)) for x in cur]
    finally:c.close()

def messages(run,family):
    output=[]
    if family=='hermes':
        for x in rows(run/'state/hermes/state.db','messages'):
            output.append(dict(database=str((run/'state/hermes/state.db').relative_to(R)),locator=x['id'],message=x))
        return output
    lib=ctypes.CDLL('libzstd.so.1')
    lib.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
    lib.ZSTD_decompress.restype=ctypes.c_size_t
    lib.ZSTD_isError.argtypes=[ctypes.c_size_t]
    for db in (run/'state/openclaw').rglob('*.sqlite'):
        if 'node_modules' in db.parts:continue
        for x in rows(db,'transcript_events'):
            text=x.get('event_json')
            if x.get('event_zstd'):
                blob=x['event_zstd'];buf=ctypes.create_string_buffer(x['event_utf8_bytes']);source=ctypes.create_string_buffer(blob)
                n=lib.ZSTD_decompress(buf,len(buf),source,len(blob))
                if lib.ZSTD_isError(n):raise RuntimeError('Native transcript decompression failed')
                text=buf.raw[:n].decode()
            obj=json.loads(text)
            if isinstance(obj.get('message'),dict):output.append(dict(database=str(db.relative_to(R)),locator=[x['session_id'],x['seq']],message=obj['message']))
    return output

def attrs(span):return {x['key']:next(iter(x['value'].values())) for x in span.get('attributes',[])}

def tool_content(msg):
    value=msg.get('content','')
    if isinstance(value,list):return '\n'.join(x.get('text','') for x in value if isinstance(x,dict))
    return value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)

def side_effect(unit,family):
    run=R/'runs-control-faults/R05-lost-commit-ack'/f'u{unit}'/family
    found=[x for x in messages(run,family) if x['message'].get('role') in ['tool','toolResult']]
    failure=[x for x in found if 'RemoteDisconnected' in tool_content(x['message'])]
    receipt=[]
    for x in found:
        text=tool_content(x['message'])
        if family=='hermes':
            try:text=json.loads(text).get('output','')
            except ValueError:continue
        try:value=json.loads(text)
        except ValueError:continue
        if isinstance(value,list) and len(value)==1 and value[0].get('id')==1 and value[0].get('body')=='controlled-one-commit':receipt.append(x)
    return dict(case='side_effect_reconstruction',unit=unit,family=family,passed=bool(failure and receipt),native_evidence=[dict(database=x['database'],locator=x['locator'],message_sha256=digest(x['message'])) for x in failure+receipt],scope='Canonical native tool failure followed by an independently queried application receipt recorded as a native tool result. The external receipt log is comparison truth only; no general exactly-once guarantee.')

def child(unit,family):
    run=R/'runs-child-recovery-native-resume/fault'/f'u{unit}'/family;token='CHILD_RESULT_OK_U'+str(unit)
    if family=='openclaw':
        db=run/'state/openclaw/state/openclaw.sqlite'
        found=[]
        for x in rows(db,'subagent_runs'):
            p=json.loads(x['payload_json']).get('parentCompletion',{})
            if p.get('completion',{}).get('resultText')==token and p.get('execution',{}).get('outcome',{}).get('status')=='ok' and x.get('requester_session_key') and x.get('child_session_key'):
                found.append(dict(run_id=x['run_id'],child=x['child_session_key'],parent=x['requester_session_key'],row_sha256=digest(x)))
    else:
        db=run/'state/hermes/state.db';found=[];sessions=rows(db,'sessions')
        for x in rows(db,'async_delegations'):
            e=json.loads(x['event_json'] or '{}');completed=[z for z in e.get('results',[]) if z.get('status')=='completed' and z.get('summary')==token]
            linked=[s for s in sessions if s.get('parent_session_id')==x.get('parent_session_id')]
            if completed and linked and x.get('state')=='unknown':found.append(dict(delegation=x['delegation_id'],parent=x['parent_session_id'],children=[z['id'] for z in linked],row_sha256=digest(x)))
    return dict(case='child_reconstruction',unit=unit,family=family,passed=bool(found),database=str(db.relative_to(R)),native_evidence=found,scope='Native durable parent/child linkage and child completion; Hermes explicitly separates retained completed child from unknown interrupted delegation. Fault timing itself is independent truth, not product audit.')

def retry(unit,family):
    run=R/'runs-observability/configured'/f'u{unit}'/family
    x=json.loads((run/'result.json').read_text());spans=x['spans']
    model=[s for s in spans if s['name']==('openclaw.model.call' if family=='openclaw' else 'openai.chat_completions')]
    failed=[s for s in model if s.get('status',{}).get('code')=='STATUS_CODE_ERROR']
    good=[s for s in model if s.get('status',{}).get('code')!='STATUS_CODE_ERROR']
    paths=[run/'gateway.log'] if family=='openclaw' else [run/'state/hermes/logs/agent.log']
    proof=[]
    for p in paths:
        for line,n in zip(p.read_text(errors='replace').splitlines(),range(1,10**8)):
            if '503' in line and ('provider=deepseek' in line or 'Controlled temporary provider failure' in line):proof.append(dict(file=str(p.relative_to(R)),line=n,sha256=hashlib.sha256(line.encode()).hexdigest()))
    linked=any(a['trace_id']==b['trace_id'] and int(a['end_time_unix_nano'])<=int(b['end_time_unix_nano']) for a in failed for b in good)
    join='native_trace_id'
    if family=='openclaw':
        # OpenClaw starts a new trace on this retry. The durable task run ID
        # remains stable; requiring identical trace topology would be bias.
        log=(run/'gateway.log').read_text(errors='replace')
        error_runs={m.group(1) for m in re.finditer(r'runId=(\S+).*?isError=true[^\n]*rawError=503',log)}
        canonical=messages(run,family)
        completed={z['message'].get('__openclaw',{}).get('runId') for z in canonical if z['message'].get('role')=='assistant' and z['message'].get('stopReason')=='stop'}
        linked=bool(error_runs & completed);join='native_error_run_id_to_canonical_completed_run'
    return dict(case='retry_reconstruction',unit=unit,family=family,passed=bool(x['truth_injected_failures']==1 and failed and good and linked and proof),native_evidence=proof,failed_span_ids=[z['span_id'] for z in failed],join=join,scope='Native model-error/HTTP503 cause and correctly linked subsequent completion. Native trace or durable run identity is accepted; identical trace topology is not required. Independent server injection is truth only.')

def approval(unit,family):
    run=R/'runs-observability/configured'/f'u{unit}'/family;x=json.loads((run/'result.json').read_text());truth=x['truth_approval_decisions'];tools=[]
    name='openclaw.tool.execution' if family=='openclaw' else 'terminal'
    for s in x['spans']:
        if s['name']!=name:continue
        a=attrs(s);call=a.get('gen_ai.tool.call.id') if family=='openclaw' else a.get('nemo_relay.tool_call_id')
        if call not in ['controlled-0-0','controlled-1-0','controlled-2-0']:continue
        text=a.get('gen_ai.tool.call.result','') if family=='openclaw' else a.get('nemo_relay.end.output','')
        ok=(('NATIVE_RESULT_first' in text) if call=='controlled-0-0' else ('NATIVE_RESULT_second' in text) if call=='controlled-1-0' else ('denied' in text.lower() and ('user-denied' in text or 'BLOCKED:' in text)))
        tools.append(dict(call=call,span_id=s['span_id'],trace_id=s['trace_id'],task=a.get('nemo_relay.end.metadata.task_id'),outcome_correct=ok))
    if family=='openclaw':
        db=run/'state/openclaw/state/openclaw.sqlite';ledger=rows(db,'operator_approvals');native=[]
        for item in truth:
            matched=[z for z in ledger if z['approval_id']==item['identity'] and z['decision']==item['choice'] and z['source_tool_call_id'] and z['source_session_key'] and z['source_run_id']]
            native.extend(dict(approval_id=z['approval_id'],decision=z['decision'],tool=z['source_tool_call_id'],resolver_kind=z['resolver_kind'],resolver_id=z['resolver_id'],row_sha256=digest(z)) for z in matched)
        exact=len(native)==3;links=exact
    else:
        # The rich native tool result associates approval/denial to task and
        # tool. Count that association as present even without a prompt UUID.
        local=run/'state/hermes/telemetry/eval-atof/events.jsonl'
        records=[json.loads(l) for l in local.read_text().splitlines()]
        human=[z for z in records if z.get('name') in ['pre_approval_request','post_approval_response','on_human_input_request','on_human_input_resolved']]
        native=[dict(name=z.get('name'),record_sha256=digest(z)) for z in human]
        exact=bool(human and all(any(t['choice'] in json.dumps(z) or (t['choice']=='allow-once' and '"once"' in json.dumps(z)) for z in human) for t in truth))
        links=len(tools)==3 and len({z['task'] for z in tools if z['task']})==1
    complete=len(tools)==3 and len({z['call'] for z in tools})==3 and all(z['outcome_correct'] for z in tools)
    return dict(unit=unit,family=family,tool_events=complete,approval_verdict_association=complete,approval_events=complete,exact_authorization_choice=exact,identity_links=bool(links and complete),native_tools=tools,native_choice_records=native,scope='The frozen common approval-event contract counts an unambiguous native task/tool/approved-or-denied association. Exact once/session/always choice is measured separately and is not imposed as an unannounced mandatory primary field. Hermes native verdict associations count positively; lack of identical UUID/schema alone is not a failure. A custom public observer can add a precise choice ledger.')

def main():
    if len(list((R/'runs-observability').glob('*/u*/*/result.json')))!=36:raise RuntimeError('Wait for all native observation profiles')
    a=[approval(u,f) for u in range(1,7) for f in ['openclaw','hermes']]
    b=[fn(u,f) for fn in [side_effect,child] for u in range(1,4) for f in ['openclaw','hermes']]
    b += [retry(u,f) for u in [2,4,6] for f in ['openclaw','hermes']]
    save(R/'results/native-observability-reconstruction.json',dict(approval=a,fault_reconstruction=b,review_status='author semantic review; colleague review pending',scope='Read-only audit of actual native outputs, canonical stores and official exporters; not a compliance/WORM archive certification.'))
    print('NATIVE_OBSERVABILITY_AUDIT',[(z['family'],z['unit'],z['approval_events'],z['identity_links']) for z in a],[(z['case'],z['family'],z['unit'],z['passed']) for z in b],flush=True)

if __name__=='__main__':main()
