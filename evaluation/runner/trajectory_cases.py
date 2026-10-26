"""Native history and public hooks joined with an independent task timeline."""
import concurrent.futures
import hashlib
import io
import json
import re
import shutil
import time

import hook_cases
import mechanism_cases
from operation_fixture import OperationFixture
import pilot
import privacy_cases
import service_path_cases as service

SCENARIOS={f'OBS-06-S{i:02}':mode for i,mode in enumerate(['model','tool','hooks','delegation','retry-cancel','redaction'],1)}
HOOK_MARKER='EVAL_NATIVE_TRAJECTORY '
HOOKS=r'''
 const trajectory=(name,event,ctx)=>{
  const out={hook:name,run_id:event.runId??ctx.runId,session_id:event.sessionId,session_key:ctx.sessionKey??event.sessionKey,
   tool_name:event.toolName,tool_call_id:event.toolCallId??ctx.toolCallId,provider:event.provider,model:event.model,
   call_id:event.callId,duration_ms:event.durationMs,upstream_request_id_hash:event.upstreamRequestIdHash,
   child_session_key:event.childSessionKey,requester_session_key:event.requesterSessionKey??ctx.requesterSessionKey,
   target_session_key:event.targetSessionKey,outcome:event.outcome,error:event.error,
   params:event.params,result:event.result,assistant_texts:event.assistantTexts,usage:event.usage,
   prompt:event.prompt,observed_unix_ms:Date.now()};
  api.logger.info('EVAL_NATIVE_TRAJECTORY '+JSON.stringify(out));
  return fetch('http://127.0.0.1:18080/trajectory',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(out)}).then(r=>r.json());
 };
 for(const name of ['model_call_started','model_call_ended','llm_input','llm_output','before_tool_call','after_tool_call','agent_end','subagent_spawned','subagent_ended'])
  api.on(name,async(event,ctx)=>{await trajectory(name,event,ctx);},{timeoutMs:3000});
'''


class TrajectoryFixture(OperationFixture):
    def __init__(self):self.hook_records=[];self.retry_token=None;self.retry_injected=False;super().__init__()
    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def do_POST(self):
                if self.path=='/trajectory':
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=65536:return self.send(dict(error='trajectory bound'),413)
                    data=json.loads(self.rfile.read(size));owner.hook_records.append(data);owner.event('native-hook-observed',**data)
                    return self.send(dict(observed=True))
                if self.path.endswith('/chat/completions') and owner.retry_token and not owner.retry_injected:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=4*1024**2:return self.send(dict(error='provider bound'),413)
                    raw=self.rfile.read(size)
                    if owner.retry_token in raw.decode(errors='replace'):
                        owner.retry_injected=True;owner.event('provider-transient-503',token=owner.retry_token)
                        return self.send(dict(error=dict(message='EVAL_TRANSIENT_PROVIDER_503',type='server_error')),503)
                    original=self.rfile;self.rfile=io.BytesIO(raw)
                    try:return super().do_POST()
                    finally:self.rfile=original
                return super().do_POST()
        return Handler


def configure(root,mode,canary):
    config=privacy_cases.configure(root,'redaction',canary) if mode=='redaction' else service.configure(root)
    config['logging']['level']='info'
    if mode=='redaction':(root/'workspace/private-memory.txt').write_text('PUBLIC_REDACTION_CONTROL '+canary+'\n')
    config['tools']['allow'].append('sessions_spawn')
    config['agents']['defaults']['subagents']=dict(maxConcurrent=2,maxSpawnDepth=1)
    plugin=root/'composition-a/index.js';source=plugin.read_text().replace(' const owner="composition-a";', ' const owner="composition-a";\n'+HOOKS)
    plugin.write_text(source);pilot.save(root/'config.json',config);return config


def native_hook_records(root):
    records=[];path=root/'gateway-native.log'
    if not path.is_file():return records
    for line in path.read_text(errors='replace').splitlines():
        try:row=json.loads(line)
        except ValueError:continue
        message=row.get('message',row.get('1',row.get('0','')))
        if not isinstance(message,str) or HOOK_MARKER not in message:continue
        try:records.append(json.loads(message.split(HOOK_MARKER,1)[1]))
        except ValueError:continue
    return records


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];token='PILOT_TRAJECTORY_'+scenario.replace('-','_')+'_U'+str(unit)
    canary='SYNTHETIC_SECRET_'+hashlib.sha256(token.encode()).hexdigest()[:40].upper()
    fixture=TrajectoryFixture();gateway=None;assertions=[];metadata={};exports=[];requests=[]
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['public-native-history-and-rpc','native-file-exported-public-hook-events','independent-provider-tool-and-hook-timeline']))
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:configure(p,mode,canary));gateway.ready()
        control=token+'_CONTROL';fixture.register(control);positive=gateway.request(control)
        if not positive['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Native trajectory receipt positive control failed')
        if not any(r['hook']=='before_tool_call' for r in fixture.hook_records):raise RuntimeError('Public observer hook positive control failed')
        row.update(native_invoked=True,fixture_validated=True)
        begin=len(fixture.hook_records);event_begin=len(fixture.events);session='agent:main:pilot:'+token.lower()
        if mode=='delegation':
            child=token+'_CHILD';fixture.register(child)
            fixture.plan(token,'sessions_spawn',dict(task='Execute the deterministic operation for '+child,mode='run',cleanup='keep',label='owned-trajectory-child'),'childSessionKey')
            result=gateway.request(token);requests.append(result)
            text=json.dumps(fixture.tool_returns.get(token,[]));matches=re.findall(r'agent:[a-z0-9_-]+:subagent:[a-zA-Z0-9-]+',text)
            metadata['spawn_tool_result']=fixture.tool_returns.get(token,[])
            if not matches:raise RuntimeError('Native spawn returned no child session identity: '+text[:1500])
            child_session=matches[0];deadline=time.monotonic()+25
            while time.monotonic()<deadline and fixture.receipts.get(child)!=1:time.sleep(.1)
            check('actual-native-child-effect-observed',fixture.receipts.get(child)==1)
            child_export=privacy_cases.history(root,child_session);exports.append(child_export)
            metadata.update(parent_session=session,child_session=child_session,child_token=child)
        elif mode=='retry-cancel':
            fixture.retry_token=token+'_RETRY';fixture.register(fixture.retry_token)
            retried=gateway.request(fixture.retry_token);requests.append(retried)
            if not fixture.retry_injected:raise RuntimeError('Declared upstream retry fault was not injected')
            metadata['retry_session']='agent:main:pilot:'+fixture.retry_token.lower()
            exports.append(privacy_cases.history(root,metadata['retry_session']))
            fixture.release.clear();fixture.register(token,gate=True)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(gateway.request,token)
                if not mechanism_cases.wait_events(fixture,'effect-start',[token],seconds=15):raise RuntimeError('Native cancellation target never reached the actual live tool gate')
                boundary=dict(request_pending_before_rpc=not future.done(),rpc_started_monotonic_ns=time.monotonic_ns())
                cancelled=hook_cases.rpc(gateway,'sessions.abort',dict(key=session));metadata.update(cancellation=cancelled,cancellation_boundary=boundary)
                fixture.release.set();result=future.result(timeout=40);requests.append(result)
            check('actual-active-cancellation-acknowledged',service.active_abort_acknowledged(cancelled,boundary))
            check('retry-task-eventually-returns-one-effect',retried['accepted'] and fixture.receipts.get(fixture.retry_token)==1)
        elif mode=='redaction':
            fixture.plan(token,'read',dict(path=str(root/'workspace/private-memory.txt')),'PUBLIC_REDACTION_CONTROL')
            result=privacy_cases.request(gateway,token,session,canary);requests.append(result)
            if canary not in json.dumps(fixture.native_inputs.get(token,[])):raise RuntimeError('Synthetic private prompt did not reach the model')
        else:
            fixture.register(token);result=gateway.request(token);requests.append(result)
        exports.append(privacy_cases.history(root,session));time.sleep(.4)
        records=native_hook_records(root);target=[r for r in records if token in json.dumps(r) or r.get('session_key')==session]
        # Public hooks share native run IDs, so events with no prompt/token are joined by those IDs.
        run_ids={r['run_id'] for r in target if r.get('run_id')}
        target=[r for r in records if r in target or r.get('run_id') in run_ids]
        independent=fixture.hook_records[begin:];history=json.dumps(exports,ensure_ascii=False);observed=json.dumps(target,ensure_ascii=False)
        check('public-history-identifies-measured-session',token in history)
        if mode=='model':
            inputs=[r for r in target if r['hook']=='llm_input'];outputs=[r for r in target if r['hook']=='llm_output']
            starts=[r for r in target if r['hook']=='model_call_started'];ends=[r for r in target if r['hook']=='model_call_ended']
            check('model-input-output-identity-open-through-public-hooks',bool(inputs and outputs) and all(r.get('provider') and r.get('model') and r.get('run_id') for r in inputs+outputs))
            start_ids={r.get('call_id') for r in starts if r.get('call_id')};end_ids={r.get('call_id') for r in ends if r.get('call_id')}
            check('model-call-start-and-end-ids-link',bool(start_ids) and start_ids==end_ids)
            metadata.update(model_call_start_count=len(starts),model_call_end_count=len(ends),upstream_request_id_hashes=[r['upstream_request_id_hash'] for r in ends if r.get('upstream_request_id_hash')],internal_model_reasoning_expected=False)
        elif mode=='tool':
            check('public-history-has-actual-tool-arguments-and-receipt','eval_probe' in history and token in history and 'RECEIPT:'+token in history)
            before=[r for r in target if r['hook']=='before_tool_call'];after=[r for r in target if r['hook']=='after_tool_call']
            check('tool-call-ids-and-duration-open',bool(before and after) and {r.get('tool_call_id') for r in before if r.get('tool_call_id')}=={r.get('tool_call_id') for r in after if r.get('tool_call_id')} and all(isinstance(r.get('duration_ms'),(int,float)) for r in after))
            check('actual-tool-result-open-through-native-hook','RECEIPT:'+token in json.dumps(after))
        elif mode=='hooks':
            names={r['hook'] for r in target}
            check('hook-events-exported-with-native-run-and-session-linkage',{'llm_input','llm_output','before_tool_call','after_tool_call','agent_end'}<=names and bool(run_ids))
            before=[e for e in fixture.events[event_begin:] if e['kind']=='native-hook-observed' and e.get('hook')=='before_tool_call']
            after=[e for e in fixture.events[event_begin:] if e['kind']=='native-hook-observed' and e.get('hook')=='after_tool_call']
            effects=[e for e in fixture.events[event_begin:] if e['kind']=='effect-commit' and e.get('token')==token]
            check('native-hook-order-agrees-with-independent-effect-timeline',bool(before and after and effects) and before[0]['monotonic_ns']<effects[0]['monotonic_ns']<after[0]['monotonic_ns'])
        elif mode=='delegation':
            spawn=[r for r in records if r['hook']=='subagent_spawned' and r.get('child_session_key')==child_session]
            check('spawn-links-native-parent-and-child',bool(spawn) and any(r.get('session_key')==session or r.get('requester_session_key')==session for r in spawn))
            check('public-child-history-identifies-actual-work',child in history)
            check('parent-tool-result-preserves-child-identity',child_session in history)
            metadata['native_child_hook_records']=[r for r in records if r.get('child_session_key')==child_session or r.get('session_key')==child_session or r.get('target_session_key')==child_session]
        elif mode=='retry-cancel':
            native_text=(root/'gateway-native.log').read_text(errors='replace')
            check('native-records-reveal-injected-provider-retry',bool(re.search(r'EVAL_TRANSIENT_PROVIDER_503|HTTP[ :]+503|(?:status|statusCode)[=: ]+503|retrying|retry attempt',native_text,re.I)))
            check('cancelled-session-has-native-causal-id',bool(run_ids))
            metadata['independent_retry_attempts']=sum(e['kind']=='provider-transient-503' or (e['kind']=='provider-request' and e.get('token')==fixture.retry_token) for e in fixture.events)
        else:
            logs=privacy_cases.wire(root,[dict(method='logs.tail',params=dict(limit=200,maxBytes=262144))]);exports.append(logs)
            check('configured-secret-redacted-from-history-and-hook-log-export',canary not in history and canary not in observed and canary not in json.dumps(logs))
            model_result=json.dumps(fixture.tool_returns.get(token,[]))
            check('configured-plaintext-source-read-is-observed-through-the-live-model-result',canary in (root/'workspace/private-memory.txt').read_text() and 'PUBLIC_REDACTION_CONTROL' in model_result)
            metadata.update(full_private_prompt_seen_by_model=canary in json.dumps(fixture.native_inputs.get(token,[])),full_secret_visible_in_live_tool_result=canary in model_result,public_read_control_seen_by_model='PUBLIC_REDACTION_CONTROL' in model_result)
        metadata.update(native_record_count=len(target),reference_observer_record_count=len(independent),native_run_ids=sorted(run_ids),
            observer_scope='Reference plugin uses documented api.on hooks and writes their supplied fields to the native logger; chat.history/logs.tail are native public RPCs. Hook fields are native provenance, but logging them requires this explicit observer plugin. Independent fixture events are truth, not injected native records.',
            model_scope='Deterministic provider transcripts measure trajectory visibility, not model quality, reasoning or real token cost.',
            raw_real_secrets_retained=False,private_runtime_imports=0)
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,
            public_native_exports=exports,native_hook_export=target,requests=requests,independent_events=fixture.events[event_begin:],
            independent_receipts=fixture.receipts,resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2200],metadata=metadata)
    finally:
        fixture.release.set()
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-3000:]
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
