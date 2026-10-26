"""Native MCP lifecycle and transport/content fidelity against owned peers."""
import concurrent.futures
import hashlib
import json
import shutil
import time

import hook_cases
from mcp_http_fixture import McpHTTPFixture,content_result
import mechanism_cases as mechanism
from operation_fixture import OperationFixture
import pilot
import service_path_cases as service

FAMILIES={'REL-13':['expired','reconnect','cancel','late-after-cancel'],
    'EXT-05':['stdio','streamable-http','sse','content-contracts']}
SCENARIOS={f'{family}-S{i:02}':name for family,names in FAMILIES.items() for i,name in enumerate(names,1)}


def configure(root,transport):
    config=service.configure(root)
    if transport=='stdio':server=dict(transport='stdio',command='/usr/bin/python3',args=['/driver/mcp_probe.py'])
    else:server=dict(transport=transport,url='http://127.0.0.1:18085/'+('sse' if transport=='sse' else 'mcp'))
    config['mcp']=dict(servers=dict(probe=dict(server,requestTimeoutMs=5000,connectionTimeoutMs=5000,supportsParallelToolCalls=True)))
    config['tools']['allow'].append('probe__eval_probe')
    pilot.save(root/'config.json',config)
    return config


def wait_started(peer,token):
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        if any(e['kind']=='mcp-tool-start' and e.get('token')==token for e in peer.events):return True
        time.sleep(.02)
    return False


def run_scenario(root,scenario,unit=1):
    family=scenario.rsplit('-S',1)[0];mode=SCENARIOS[scenario]
    transport=mode if family=='EXT-05' and mode in {'stdio','sse','streamable-http'} else 'streamable-http'
    fixture=OperationFixture();peer=None if transport=='stdio' else McpHTTPFixture(transport);gateway=None
    token='PILOT_MCP_CONTRACT_'+scenario.replace('-','_')+'_U'+str(unit)
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    assertions=[];requests=[];metadata={}
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-tool-returns','independent-mcp-events','independent-receipts']))
    def plan(item,**options):
        fixture.plan(item,'probe__eval_probe',dict(token=item,action='effect',unicode='π_中文_🙂'),'RECEIPT:'+item)
        if peer:peer.register(item,**options)
    def request(item):
        result=gateway.request(item);requests.append({k:v for k,v in result.items() if k!='response_excerpt'});return result
    def receipt(item):return (peer.receipts if peer else fixture.receipts).get(item,0)
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:configure(p,transport));gateway.ready()
        control=token+'_CONTROL';fixture.register(control);positive=request(control)
        if not positive['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Native Gateway positive control failed')
        mcp_control=token+'_MCP_CONTROL';plan(mcp_control);native=request(mcp_control)
        if not native['accepted'] or receipt(mcp_control)!=1:raise RuntimeError('Owned '+transport+' MCP transport positive control failed: '+json.dumps(native)[:1200])
        row.update(fixture_validated=True,native_invoked=True)
        if family=='EXT-05':
            formats=['text','structured','resource','unicode','large'] if mode=='content-contracts' else ['text']
            for format in formats:
                item=token+'_'+format.upper();plan(item,format=format);result=request(item)
                returned=fixture.tool_returns.get(item,[]);text=json.dumps(returned,ensure_ascii=False)
                check(format+'-response-retains-tool-identity-and-receipt',result['accepted'] and receipt(item)==1)
                if format=='structured':check('structured-only-content-preserved','STRUCTURED_ONLY_'+item in text)
                if format=='resource':check('embedded-resource-uri-and-text-preserved','eval-fixture://owned/'+item in text and 'RESOURCE_BODY_'+item in text)
                if format=='unicode':check('unicode-content-fidelity',all(v in text for v in ['π','中文','🙂','END_'+item]))
                if format=='large':
                    payload='q'*(32*1024)
                    check('full-32kib-result-accessible',payload in text and 'LARGE_BEGIN_'+item in text and 'LARGE_END_'+item in text)
                    metadata['large_payload_sha256']=hashlib.sha256(payload.encode()).hexdigest()
                if peer:
                    starts=[e for e in peer.events if e['kind']=='mcp-tool-start' and e.get('token')==item]
                    check(format+'-arguments-delivered-without-unicode-corruption',len(starts)==1 and starts[0]['arguments'].get('unicode')=='π_中文_🙂')
            metadata['content_scope']='Actual public native MCP dispatch. Large is predeclared as 32 KiB, not an unbounded result or resource-fetch claim.'
        elif mode in {'expired','reconnect'}:
            plan(token,drop_after_commit=mode=='reconnect')
            if mode=='expired':peer.expire_on_tokens.add(token)
            result=request(token)
            if mode=='expired' and not any(e['kind']=='mcp-live-session-expiry-injected' and e.get('token')==token for e in peer.events):
                raise RuntimeError('Declared native session expiry was not injected on the actual live tool call')
            check('ambiguous-or-expired-call-not-falsely-completed',not result['accepted'])
            check('failed-call-not-replayed',receipt(token)==(1 if mode=='reconnect' else 0))
            after=token+'_NEXT_DISCOVERY';plan(after);next_result=request(after)
            check('subsequent-native-discovery-can-reconnect',next_result['accepted'] and receipt(after)==1)
            if mode=='expired':check('expired-session-actually-rejected',any(e['kind']=='mcp-session-rejected' for e in peer.events))
            else:check('effect-commit-precedes-actual-connection-loss',any(e['kind']=='mcp-connection-dropped-after-effect' for e in peer.events))
            metadata['replay_contract']='The pinned native contract reports the failed call without replaying it, then retires an expired connection for later discovery; an external effect can already have committed.'
        else:
            peer.release.clear();plan(token,gate=True,commit_before_gate=mode=='late-after-cancel',ignore_cancel=mode=='late-after-cancel')
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pending=pool.submit(request,token)
                if not wait_started(peer,token):raise RuntimeError('Actual MCP call failed to reach the cancellation gate')
                boundary=dict(request_pending_before_rpc=not pending.done(),rpc_started_monotonic_ns=time.monotonic_ns())
                cancellation=hook_cases.rpc(gateway,'sessions.abort',dict(key='agent:main:pilot:'+token.lower()))
                boundary['rpc_returned_monotonic_ns']=time.monotonic_ns()
                peer.release.set();boundary['peer_gate_released_monotonic_ns']=time.monotonic_ns()
                result=pending.result(timeout=40)
            time.sleep(.5)
            check('native-active-cancellation-acknowledged',service.active_abort_acknowledged(cancellation,boundary))
            check('cancelled-native-task-not-falsely-completed',not result['accepted'])
            if mode=='cancel':
                check('cooperative-remote-operation-cancelled-before-effect',receipt(token)==0)
                check('mcp-cancel-notification-linked-to-live-call',any(e['kind']=='mcp-cancel-notification' and e.get('matched') for e in peer.events))
            else:
                check('already-committed-effect-not-duplicated',receipt(token)==1)
                check('late-response-actually-attempted',any(e['kind']=='mcp-tool-return-attempt' and e.get('token')==token for e in peer.events))
            after=token+'_UNRELATED';plan(after);next_result=request(after)
            new_return=json.dumps(fixture.tool_returns.get(after,[])).replace('RECEIPT:'+after,'')
            check('new-call-not-confused-with-old-late-response',next_result['accepted'] and receipt(after)==1 and 'RECEIPT:'+token not in new_return)
            metadata.update(cancellation=cancellation,cancellation_boundary=boundary,
                cancellation_contract='S03 peer cooperatively honors a received MCP cancel notification before committing. S04 commits before cancellation and deliberately attempts a late return. Prior committed effects are never classified as prevented effects.')
        if peer:check('no-fixture-gate-timeout',not any(e['kind']=='mcp-fixture-gate-timeout' for e in peer.events))
        metadata.update(transport=transport,public_api_only=True,core_edits=0,private_imports=0)
        returns={key:value for key,value in fixture.tool_returns.items() if key.startswith(token)}
        # Retain actual native return bytes for full-result fidelity, bounded by
        # the explicit 32 KiB large case and existing 1 MiB summary budget.
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            metadata=metadata,requests=requests,native_tool_returns=returns,independent_mcp_events=peer.events if peer else [],
            independent_receipts=peer.receipts if peer else fixture.receipts,independent_fixture_events=fixture.events,
            resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2500],metadata=metadata)
    finally:
        if peer:peer.release.set()
        if gateway:gateway.stop()
        if peer:peer.close()
        fixture.close();shutil.rmtree(root,ignore_errors=True)
        row['owned_state_retained']=root.exists()
    return row
