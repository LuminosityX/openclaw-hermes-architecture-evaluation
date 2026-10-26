"""Lost acknowledgments at an actual native MCP effect boundary, in both key arms."""
import concurrent.futures
import json
import os
import shutil
import signal
import time

from mcp_http_fixture import McpHTTPFixture,content_result
from operation_fixture import OperationFixture
import pilot
import recovery_cases
import service_path_cases as service

SCENARIOS={f'REL-02-S{i:02}':name for i,name in enumerate(['before-commit','after-commit','owner-death'],1)}


class EffectPeer(McpHTTPFixture):
    def __init__(self):
        self.drop_before=set();self.idempotent=set()
        super().__init__()

    def response(self,body,session_id):
        if body.get('method')=='tools/call':
            token=body.get('params',{}).get('arguments',{}).get('token')
            if token in self.drop_before:
                self.drop_before.remove(token);self.sessions[session_id]['valid']=False
                self.event('mcp-loss-before-effect',token=token,generation=self.sessions[session_id]['generation'])
                return dict(_drop_connection=True)
            if token in self.idempotent and self.receipts.get(token):
                self.event('mcp-idempotency-reuse',token=token,generation=self.sessions[session_id]['generation'])
                return dict(jsonrpc='2.0',id=body['id'],result=content_result(token))
        return super().response(body,session_id)


def configure(root):
    config=service.configure(root)
    config['mcp']=dict(servers=dict(effects=dict(transport='streamable-http',url='http://127.0.0.1:18085/mcp',supportsParallelToolCalls=True,requestTimeoutMs=10000,connectionTimeoutMs=5000)))
    config['tools']['allow'].append('effects__eval_probe');pilot.save(root/'config.json',config);return config


def wait_control(gateway,fixture,token):
    """Bounded evaluator readiness probe, never replay a dispatched operation."""
    fixture.register(token);deadline=time.monotonic()+30;attempts=[]
    while True:
        result=gateway.request(token);attempts.append(result)
        seen=any(e.get('token')==token and 'provider' in e['kind'] for e in fixture.events)
        if not recovery_cases.pending_admission(result,''.join(gateway.log_tail),seen,fixture.receipts.get(token,0)) or time.monotonic()>=deadline:break
        time.sleep(.5)
    if not result['accepted'] or fixture.receipts.get(token)!=1:raise RuntimeError('Native service/effect positive control failed: '+json.dumps(result)[:1800])
    return attempts


def run_scenario(root,scenario,unit=1,native_observer=None):
    mode=SCENARIOS[scenario];fixture=OperationFixture();peer=EffectPeer();gateway=None;assertions=[];arms=[]
    token='PILOT_EFFECT_RECOVERY_'+scenario.replace('-','_')+'_U'+str(unit)
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['actual-mcp-fault-boundary','independent-effect-ledger','native-result-and-process-records']))
    def plan(item,effect):fixture.plan(item,'effects__eval_probe',dict(token=effect),'RECEIPT:'+effect)
    try:
        gateway=pilot.Gateway(root,configurer=configure);gateway.ready();wait_control(gateway,fixture,token+'_CONTROL')
        native_control=token+'_MCP_CONTROL';peer.register(native_control);plan(native_control,native_control)
        if not gateway.request(native_control)['accepted'] or peer.receipts.get(native_control)!=1:raise RuntimeError('Native effect transport control failed')
        row.update(native_invoked=True,fixture_validated=True)
        for keyed in [False,True]:
            item=token+('_KEYED' if keyed else '_UNKEYED');effect=item+'_EFFECT'
            peer.register(effect,drop_after_commit=mode=='after-commit',gate=mode=='owner-death',commit_before_gate=mode=='owner-death')
            if keyed:peer.idempotent.add(effect)
            if mode=='before-commit':peer.drop_before.add(effect)
            plan(item,effect)
            if mode=='owner-death':
                peer.release.clear()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pending=pool.submit(gateway.request,item)
                    deadline=time.monotonic()+12
                    while time.monotonic()<deadline and not peer.receipts.get(effect):time.sleep(.02)
                    if peer.receipts.get(effect)!=1:peer.release.set();raise RuntimeError('Actual pre-result effect commit gate was not reached')
                    killed_pid=gateway.process.pid;os.killpg(killed_pid,signal.SIGKILL);gateway.process.wait(timeout=5)
                    peer.release.set();result=pending.result(timeout=40)
                check(item+'-owner-actually-exited',gateway.process.poll() is not None)
                gateway.stop();gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready()
                recovery=wait_control(gateway,fixture,item+'_RESTART_CONTROL')
            else:
                result=gateway.request(item);recovery=[]
            count_before_retry=peer.receipts.get(effect,0)
            expected=0 if mode=='before-commit' else 1
            boundary=any(e.get('token')==effect and e['kind']==('mcp-loss-before-effect' if mode=='before-commit' else 'mcp-effect-commit') for e in peer.events)
            if not boundary:raise RuntimeError('Declared actual effect/loss boundary was not injected')
            check(item+'-no-false-native-completion',not result['accepted'])
            check(item+'-no-automatic-effect-replay',count_before_retry==expected)
            peer.tasks[effect].update(drop_after_commit=False,gate=False,commit_before_gate=False)
            retry=item+'_EXPLICIT_OPERATOR_RETRY';plan(retry,effect);retried=gateway.request(retry)
            expected_retry=1 if keyed or mode=='before-commit' else 2
            check(item+'-explicit-retry-result-matches-independent-ledger',retried['accepted'] and peer.receipts.get(effect,0)==expected_retry)
            arms.append(dict(idempotency_key=effect if keyed else None,first_request=result,post_restart_controls=recovery,
                effects_before_operator_retry=count_before_retry,explicit_operator_retry=retried,effects_after_operator_retry=peer.receipts.get(effect,0),
                automatic_reconciliation_observed=False,operator_retry_count=1,
                uncertainty='Committed effect is visible only to the independent ledger when native acknowledgement is lost; scripted provider does not invent successful reconciliation.'))
        if native_observer:row['native_observer_export']=native_observer(root,token)
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            arms=arms,independent_effects=peer.receipts,independent_mcp_events=peer.events,native_provider_events=fixture.events,
            metadata=dict(mode=mode,public_api_only=True,core_edits=0,
                idempotency_contract='The synthetic remote peer deduplicates the stable owned effect key only in the keyed arm. The unkeyed explicit operator retry is expected to repeat the effect; it is reported separately from framework automatic replay.'),
            resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2500],arms=arms)
    finally:
        peer.release.set()
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-3000:]
        peer.close();fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
