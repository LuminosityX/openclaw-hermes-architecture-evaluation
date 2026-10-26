"""A frozen deterministic diagnostician; accepts native records, never fault labels."""
import re

FIELDS={'server_ack','client_wire','history','child_history','operator_requests','operator_responses','approval_history','policy_records','external_histories','native_commits'}


def blind_native_records(records):
    aliases={}
    def text(value):
        def substitute(match):
            key=match.group().lower()
            if key not in aliases:aliases[key]='OPAQUE_TASK_'+str(len(aliases)+1)
            return aliases[key]
        return re.sub(r'PILOT_[A-Z0-9_]+',substitute,value,flags=re.I)
    def visit(value):
        if isinstance(value,dict):return {text(k):visit(value[k]) for k in sorted(value)}
        if isinstance(value,list):return [visit(v) for v in value]
        return text(value) if isinstance(value,str) else value
    return visit({k:records.get(k,[] if k.endswith('s') else {}) for k in sorted(FIELDS)})


def diagnose_native(records):
    selected={key:records.get(key) for key in FIELDS}
    def walk(value):
        if isinstance(value,dict):
            yield value
            for child in value.values():yield from walk(child)
        elif isinstance(value,list):
            for child in value:yield from walk(child)
    nodes=list(walk(selected));history_nodes=list(walk(selected.get('history')));child_nodes=list(walk(selected.get('child_history')))
    requests=selected.get('operator_requests') or [];responses=selected.get('operator_responses') or []
    pairs=[(request,response) for request in requests for response in responses if request.get('id') and request.get('id')==response.get('id')]
    parent_keys={n[k] for n in history_nodes for k in ['sessionKey','key'] if isinstance(n.get(k),str) and n[k].startswith('agent:')}
    links={n[k] for n in child_nodes for k in ['spawnedBy','parentSessionKey','parentKey'] if isinstance(n.get(k),str)}
    stopped=any(request.get('method')=='sessions.abort' and request.get('params',{}).get('key') in parent_keys and response.get('ok')
        and response.get('payload',{}).get('status')=='aborted' for request,response in pairs)
    approval=any(n.get('status')=='allowed' and n.get('decision')=='allow-once' for n in nodes)
    readonly=any(n.get('permissionMode')=='read-only' for n in history_nodes+list(walk(selected.get('policy_records'))))
    policy_request=any(request.get('method')=='sessions.patch' and request.get('params',{}).get('permissionMode')=='read-only'
        and request.get('params',{}).get('key') in parent_keys for request,response in pairs)
    ack=selected.get('server_ack') or {};wire=selected.get('client_wire') or {}
    ack_join=ack.get('id') and any(e.get('kind')=='rpc-request-written' and e.get('method')=='chat.send' and e.get('request_id')==ack['id'] for e in wire.get('events',[]))
    interrupted=any(r.get('error',{}).get('code')=='SOCKET_CLOSED' for r in wire.get('responses',[]))
    committed=bool((selected.get('native_commits') or {}).get('matches'))
    errors=[n for n in nodes if n.get('role')=='toolResult' and n.get('isError') is True]
    diagnosis='under-determined';boundary=False;uncertainties=[]
    if ack.get('ok') and ack_join and interrupted and committed:
        diagnosis='acknowledgment-path-interrupted';boundary=True
        uncertainties.append('Selected native records do not uniquely separate a process crash from a transport cut.')
    elif stopped and parent_keys&links:
        diagnosis='delegated-work-interrupted';boundary=any(n.get('abortedLastRun') is True for n in child_nodes)
        uncertainties.append('A Stop ACK and native child termination do not prove the state of every external side effect.')
    elif approval and readonly and policy_request:
        diagnosis='approval-revocation-window'
        uncertainties.append('A grant and saved policy transition alone do not bind the exact launch to a policy version or external effect-commit point.')
    elif errors:
        diagnosis='external-tool-result-ambiguous'
        uncertainties.append('A failed native tool result cannot reveal whether the remote effect committed before its reply was lost.')
    else:uncertainties.append('Selected native records do not establish one supported causal hypothesis.')
    identifiers=sorted({n[k] for n in nodes for k in ['id','runId','sessionKey','key','toolCallId'] if isinstance(n.get(k),str) and n[k]})
    return dict(diagnosis=diagnosis,exact_boundary_reconstructed=boundary,external_faulted_effect_commit='unknown',
        uncertainties=uncertainties,native_identifiers=identifiers[:40],
        scope='Registered structured-record consumer, not a human or model capability benchmark. Unknowns remain unknown; no fault injection or independent effect truth is accepted.')
