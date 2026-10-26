"""Native delegated runs, real owner lease expiry and late external results."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import time

from authorization_observation_cases import AuthorizationFixture
from effect_recovery_cases import wait_control
from mcp_contract_cases import wait_started
from mcp_http_fixture import McpHTTPFixture
import native_freeze
import pilot
import privacy_cases
import service_path_cases as service

SCENARIOS={f'REL-03-S{i:02}':mode for i,mode in enumerate(['parent-restart','child-restart','expired-owner'],1)}


def owner_lease(root):
    rows=[]
    for path in (root/'state').rglob('*.sqlite'):
        connection=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=2)
        try:
            if not connection.execute("select 1 from sqlite_master where type='table' and name='state_leases'").fetchone():continue
            for owner,expiry,heartbeat,payload in connection.execute("select owner,expires_at,heartbeat_at,payload_json from state_leases NOT INDEXED where scope='gateway-owner' and lease_key='global' limit 2"):
                data=json.loads(payload);rows.append(dict(database=str(path.relative_to(root)),owner_sha256=hashlib.sha256(owner.encode()).hexdigest(),expires_at_ms=expiry,heartbeat_at_ms=heartbeat,pid=data.get('owner',{}).get('pid'),port=data.get('port'),observed_at_ms=int(time.time()*1000)))
        finally:connection.close()
    if len(rows)!=1:raise RuntimeError('Actual native Gateway owner lease is missing or ambiguous')
    return rows[0]


def configure(root):
    config=service.configure(root);config['tools']['allow'].append('sessions_spawn')
    config['agents']['defaults']['timeoutSeconds']=600;config['agents']['defaults']['subagents']=dict(maxConcurrent=2,maxSpawnDepth=1,runTimeoutSeconds=600)
    config['mcp']=dict(servers=dict(delegated=dict(transport='streamable-http',url='http://127.0.0.1:18085/mcp',requestTimeoutMs=480000,connectionTimeoutMs=5000)))
    config['tools']['allow'].append('delegated__eval_probe');pilot.save(root/'config.json',config);return config


def child_active(history):
    return any(response.get('result',{}).get('payload',{}).get('sessionInfo',{}).get('hasActiveRun') for response in history.get('responses',[]))


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];token='PILOT_DELEGATION_'+scenario.replace('-','_')+'_U'+str(unit)
    fixture=AuthorizationFixture();peer=McpHTTPFixture(gate_timeout_seconds=480);gateway=None;candidate=None;metadata={};requests=[];assertions=[];frozen=False
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['actual-native-subagent-and-session-records','independent-MCP-effect-and-late-reply-events','actual-kernel-runtime-freeze-and-native-owner-lease']))
    def capture(key):return privacy_cases.history(root,key)
    try:
        gateway=pilot.Gateway(root,configurer=configure,native_cgroup=True);gateway.ready();wait_control(gateway,fixture,token+'_READY')
        control=token+'_MCP_CONTROL';peer.register(control);fixture.plan(control,'delegated__eval_probe',dict(token=control),'RECEIPT:'+control)
        if not gateway.request(control)['accepted'] or peer.receipts.get(control)!=1:raise RuntimeError('Native delegated MCP transport positive control failed')
        child=token+'_CHILD';effect=token+'_EXTERNAL_EFFECT';peer.register(effect,gate=True,commit_before_gate=mode!='parent-restart',ignore_cancel=True);peer.release.clear()
        fixture.child_tokens.add(child);fixture.plan(child,'delegated__eval_probe',dict(token=effect),'RECEIPT:'+effect)
        parent=token+'_PARENT';fixture.plan(parent,'sessions_spawn',dict(task='Execute the deterministic operation for '+child,mode='run',cleanup='keep',label='owned-delegation-fault-child'),'childSessionKey')
        result=gateway.request(parent);requests.append(result);returned=json.dumps(fixture.tool_returns.get(parent,[]));matches=re.findall(r'agent:[a-z0-9_-]+:subagent:[a-zA-Z0-9-]+',returned)
        if not result['accepted'] or not matches or not wait_started(peer,effect):raise RuntimeError('Actual parent spawn and live child operation were not established')
        child_session=matches[0];before=capture(child_session)
        if not child_active(before):raise RuntimeError('Actual child had no native live-run evidence before intervention')
        if mode!='parent-restart' and peer.receipts.get(effect)!=1:raise RuntimeError('Actual remote effect did not commit before the declared child/owner boundary')
        metadata.update(actual_child_session=child_session,native_spawn_result=fixture.tool_returns.get(parent,[]),native_child_before=before,old_gateway_pid=gateway.process.pid)
        row.update(native_invoked=True,fixture_validated=True)
        if mode=='child-restart':
            cancelled=privacy_cases.wire(root,[dict(method='sessions.abort',params=dict(key=child_session))]);metadata['native_child_stop']=cancelled
            fixture.completed_child_tokens.add(child);peer.release.set();deadline=time.monotonic()+15
            after=capture(child_session)
            while child_active(after) and time.monotonic()<deadline:time.sleep(.3);after=capture(child_session)
            check('actual-child-run-stops-without-restarting-parent-Gateway',not child_active(after) and gateway.process.pid==metadata['old_gateway_pid'])
        else:
            fixture.completed_child_tokens.add(child)
            if mode=='expired-owner':
                before_lease=owner_lease(root);scope=native_freeze.members()
                if before_lease['pid'] not in scope or os.getpid() in scope:raise RuntimeError('Native persisted owner does not belong to the isolated runtime freeze scope')
                events=native_freeze.freeze(True);frozen=True;lease=owner_lease(root);until=time.monotonic()+330
                if not isinstance(lease['expires_at_ms'],int) or lease['expires_at_ms']-lease['observed_at_ms']>310000:raise RuntimeError('Native owner lease does not have the pinned finite five-minute lifetime')
                while lease['expires_at_ms']>=int(time.time()*1000) and time.monotonic()<until:
                    time.sleep(min(1,max(.01,(lease['expires_at_ms']-int(time.time()*1000))/1000)));lease=owner_lease(root)
                if lease['expires_at_ms']>=int(time.time()*1000) or lease['owner_sha256']!=before_lease['owner_sha256']:raise RuntimeError('Actual old native lease did not expire under the proven runtime freeze')
                metadata.update(native_lease_before=before_lease,native_lease_expired=lease,kernel_freeze_events=events,frozen_native_pids=scope)
                candidate=pilot.Gateway(root,configurer=service.reuse,port=18790)
                try:candidate.ready(timeout=12);second_ready=True
                except RuntimeError as error:second_ready=False;metadata['native_second_owner_probe_error']=str(error)[-2500:]
                metadata['native_second_owner_probe']=dict(port=18790,ready=second_ready,returncode=candidate.process.poll(),native_tail=''.join(candidate.log_tail)[-2500:])
                lease_after_probe=owner_lease(root)
                check('expired-logical-lease-does-not-replace-a-still-live-physical-coordinator',not second_ready and lease_after_probe['owner_sha256']==before_lease['owner_sha256'])
                candidate.stop();candidate=None
            native_freeze.kill();gateway.process.wait(timeout=5)
            if frozen:native_freeze.freeze(False);frozen=False
            gateway.stop();gateway=pilot.Gateway(root,configurer=service.reuse,native_cgroup=True);gateway.ready();wait_control(gateway,fixture,token+'_RESTART_READY')
            metadata['new_gateway_pid']=gateway.process.pid
            if mode=='expired-owner':
                new_lease=owner_lease(root);metadata['native_new_owner_lease']=new_lease
                check('physical-owner-death-allows-a-distinct-native-owner',new_lease['owner_sha256']!=metadata['native_lease_before']['owner_sha256'])
            peer.release.set();deadline=time.monotonic()+15
            after=capture(child_session)
            while child_active(after) and time.monotonic()<deadline:time.sleep(.3);after=capture(child_session)
            check('native-interrupted-child-does-not-remain-phantom-running',not child_active(after))
        deadline=time.monotonic()+3
        while time.monotonic()<deadline and not any(e['kind']=='mcp-tool-return-attempt' and e.get('token')==effect for e in peer.events):time.sleep(.05)
        after=capture(child_session);metadata['native_child_after_late_response']=after
        check('late-old-operation-result-does-not-attach-as-a-new-child-success','RECEIPT:'+effect not in json.dumps(after))
        check('old-delegated-operation-is-not-automatically-replayed',peer.receipts.get(effect,0)==1)
        metadata['effects_before_explicit_operator_retry']=peer.receipts.get(effect,0)
        if mode=='child-restart':
            resumed=token+'_EXPLICIT_CONTINUATION';peer.register(effect);fixture.plan(resumed,'delegated__eval_probe',dict(token=effect),'RECEIPT:'+effect)
            continued=privacy_cases.wire(root,[dict(method='sessions.send',params=dict(key=child_session,message=resumed+'\nExplicit operator continuation after interruption. Retry the owned operation without assuming that earlier remote effects were rolled back.',idempotencyKey=token+'_EXPLICIT_OPERATOR_RETRY',timeoutMs=45000))]);requests.append(continued)
            responses=continued.get('responses',[]);accepted=bool(responses) and all(r.get('result',{}).get('ok') for r in responses)
            deadline=time.monotonic()+45;after_resume=capture(child_session)
            while accepted and time.monotonic()<deadline and (child_active(after_resume) or peer.receipts.get(effect,0)<2):
                time.sleep(.3);after_resume=capture(child_session)
            metadata.update(explicit_operator_continuation=continued,native_child_after_explicit_continuation=after_resume,effects_after_explicit_operator_retry=peer.receipts.get(effect,0),continuation_entry_point='Documented operator sessions.send; generic HTTP completions intentionally rejects reserved internal namespaces')
            before_payload=before.get('responses',[{}])[0].get('result',{}).get('payload',{});after_payload=after_resume.get('responses',[{}])[0].get('result',{}).get('payload',{})
            check('retained-child-conversation-accepts-explicit-native-continuation',accepted and after_resume.get('responses',[{}])[0].get('result',{}).get('ok') is True and resumed in json.dumps(after_resume) and before_payload.get('sessionId')==after_payload.get('sessionId') and peer.receipts.get(effect,0)>=2 and 'RECEIPT:'+effect in json.dumps(after_resume))
            metadata['retry_scope']='Any extra unkeyed effect after this explicit operator retry is recorded as operator replay, not framework automatic replay or an exactly-once promise.'
        neighbor=token+'_UNRELATED';fixture.register(neighbor);result=gateway.request(neighbor);requests.append(result)
        check('unrelated-native-work-remains-usable',result['accepted'] and fixture.receipts.get(neighbor)==1)
        if any(e['kind']=='mcp-fixture-gate-timeout' for e in peer.events):raise RuntimeError('Owned external gate timed out; native fault timing is invalid')
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,resources=gateway.sampler.summary(),paid_model_calls=0,
            scope='Actual native sessions_spawn child plus its independently hosted MCP operation. Parent/Gateway restart stops in-process native loops; an external operation can continue. Child restart means stopping and explicitly continuing its retained native session while the same Gateway stays live. Five-minute native coordinator lease expiry is observed without editing timestamps. Logical expiry is distinguished from the separate physical coordinator fence. Reference notifications never choose an implicit business retry.')
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2400],metadata=metadata)
    finally:
        peer.release.set();fixture.allow_model.set()
        if frozen:native_freeze.kill();native_freeze.freeze(False)
        if candidate:candidate.stop()
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-3500:]
        row.update(requests=requests,native_tool_returns=fixture.tool_returns,independent_external_events=peer.events,independent_external_effects=peer.receipts,independent_provider_events=fixture.events)
        peer.close();fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
