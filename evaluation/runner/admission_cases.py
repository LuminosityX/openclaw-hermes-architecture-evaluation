"""Actual public chat.send ACK, committed custody and pre-worker crash boundaries."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import subprocess
import threading
import time
import uuid

from effect_recovery_cases import wait_control
import mechanism_cases
from operation_fixture import OperationFixture
import pilot
import privacy_cases
import service_path_cases as service

SCENARIOS={f'REL-01-S{i:02}':mode for i,mode in enumerate(['before-append','before-client-ack','after-client-ack'],1)}


def committed_matches(root,token):
    matches=[];examined=0;exact=re.compile(rb'(?<![A-Z0-9_])'+re.escape(token.encode())+rb'(?![A-Z0-9_])')
    for path in sorted(root.rglob('*.sqlite')):
        if path.stat().st_size>8*1024**2:raise RuntimeError('Owned admission SQLite inspection exceeds its declared bound')
        connection=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=2)
        try:
            tables=[v[0] for v in connection.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
            for table in tables:
                for values in connection.execute('select * from "'+table.replace('"','""')+'" limit 500'):
                    fragments=[v if isinstance(v,str) else v.decode(errors='ignore') for v in values if isinstance(v,(str,bytes))]
                    raw=' '.join(fragments).encode();examined+=len(raw)
                    if examined>16*1024**2:raise RuntimeError('Owned admission committed-row inspection exceeds its total bound')
                    if exact.search(raw):matches.append(dict(database=str(path.relative_to(root)),table=table,row_sha256=hashlib.sha256(repr(values).encode()).hexdigest()))
        finally:connection.close()
    return dict(matches=matches,examined_text_bytes=examined,scope='Independent read-only SQLite connections, at most 500 rows per table and 16 MiB text total. A negative scan alone is not a global absence proof.')


def admitted_run(probe,session,run_id):
    for response in probe.get('responses',[]):
        result=response.get('result',{});info=result.get('payload',{}).get('sessionInfo',{})
        payload=result.get('payload',{})
        matched=run_id in info.get('activeRunIds',[]) or payload.get('inFlightRun',{}).get('runId')==run_id
        if result.get('ok') and info.get('key')==session and info.get('hasActiveRun') and matched:return True
    return False


class AdmissionFixture(OperationFixture):
    def __init__(self):
        self.wire_events=[];self.held=threading.Event();self.wire_release=threading.Event();self.wire_release.set();self.client_result=threading.Event()
        super().__init__();self.gate_timeout_seconds=30
    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def do_POST(self):
                if self.path!='/admission-wire':return super().do_POST()
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=65536:return self.send(dict(error='owned-admission-wire-bound'),413)
                body=json.loads(self.rfile.read(size));body['monotonic_ns']=time.monotonic_ns();owner.wire_events.append(body)
                if body.get('kind') in {'target-request-held-before-forwarding','native-ack-held-before-client'}:
                    owner.held.set()
                    if not owner.wire_release.wait(timeout=18):owner.event('admission-wire-gate-timeout');return self.send(dict(error='gate-timeout'),504)
                if body.get('kind')=='actual-client-rpc-result':owner.client_result.set()
                return self.send(dict(observed=True))
        return Handler


def configure(root):
    config=service.configure(root);config['agents']['defaults']['maxConcurrent']=1
    config['gateway']['controlUi'].update(enabled=True,allowedOrigins=['http://127.0.0.1:18789'])
    pilot.save(root/'config.json',config);return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];token='PILOT_ADMISSION_'+scenario.replace('-','_')+'_U'+str(unit)
    session='agent:main:pilot:'+token.lower();fixture=AdmissionFixture();gateway=None;wire=None;requests=[];metadata={};assertions=[]
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['actual-native-request-and-ACK-frames','independent-committed-custody-records','actual-pre-dispatch-queue-and-effect-ledger']))
    def launch(selected_mode):
        spec=root/('admission-'+selected_mode+'.json')
        pilot.save(spec,dict(shared_token=pilot.TOKEN,mode=selected_mode,token=token,session_key=session,idempotency_key=identity,identity_path=str(root/'owned-wire-identity.json')))
        child=subprocess.Popen([pilot.NODE,'/driver/admission_wire.mjs',str(spec)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        first=child.stdout.readline()
        if not first.strip() or not json.loads(first).get('ready'):
            child.kill();output,error=child.communicate(timeout=5)
            raise RuntimeError('Owned admission wire failed native owner/health positive control: '+first[:800]+error[-1000:])
        return child
    def settle(child):
        child.stdin.write('finish\n');child.stdin.flush();output,error=child.communicate(timeout=12)
        if child.returncode:raise RuntimeError('Actual admission wire failed: '+output[-1500:]+error[-1000:])
        return json.loads(output.strip().splitlines()[-1])
    try:
        gateway=pilot.Gateway(root,configurer=configure);gateway.ready();wait_control(gateway,fixture,token+'_READY')
        # Prove the exact public admission method, not only the HTTP adapter.
        control=token+'_WIRE_CONTROL';fixture.register(control)
        positive=privacy_cases.wire(root,[dict(method='chat.send',params=dict(sessionKey='agent:main:pilot:'+control.lower(),message='Execute the deterministic operation for '+control,idempotencyKey=str(uuid.uuid4())))])
        if not positive['responses'][0]['result'].get('ok'):raise RuntimeError('Native chat.send admission positive control failed: '+json.dumps(positive)[:1500])
        deadline=time.monotonic()+20
        while time.monotonic()<deadline and fixture.receipts.get(control)!=1:time.sleep(.1)
        if fixture.receipts.get(control)!=1:raise RuntimeError('Actual native admitted control did not dispatch and complete')
        metadata['native_chat_send_control']=positive;fixture.register(token);identity=str(uuid.uuid5(uuid.NAMESPACE_URL,token))
        initialized=token+'_TARGET_SESSION_READY';fixture.register(initialized)
        prepared=gateway.request(initialized,session_key=token.lower())
        if not prepared['accepted'] or fixture.receipts.get(initialized)!=1:raise RuntimeError('Actual initialized native session required by restart-safe admission was not established')
        metadata['target_session_initialization']=prepared
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            blocker=None
            if mode!='before-append':
                blocking=token+'_BLOCKER';fixture.register(blocking,gate=True);fixture.release.clear();blocker=pool.submit(gateway.request,blocking)
                if not mechanism_cases.wait_events(fixture,'effect-start',[blocking],seconds=12):raise RuntimeError('Actual native worker slot was not occupied before admission fault')
            fixture.wire_release.clear();wire=launch(mode)
            if mode=='after-client-ack':
                if not fixture.client_result.wait(timeout=12):raise RuntimeError('Native ACK was not actually received by the client before the fault')
                ack=next(e['native_response'] for e in fixture.wire_events if e['kind']=='actual-client-rpc-result')
            else:
                if not fixture.held.wait(timeout=12):raise RuntimeError('Actual requested admission wire boundary was not reached')
                ack=next((e['native_response'] for e in fixture.wire_events if e['kind']=='native-ack-held-before-client'),None)
            if mode!='before-append' and not ack.get('ok'):raise RuntimeError('Held/received native chat.send response was not a successful ACK: '+json.dumps(ack)[:1200])
            durable=committed_matches(root,token);metadata['committed_records_before_fault']=durable
            if mode!='before-append':
                queued=privacy_cases.history(root,session);metadata['native_pre_fault_queue']=queued
                if not admitted_run(queued,session,ack['payload'].get('runId')):raise RuntimeError('Acknowledged target lacked native custody linked to its exact ACK run ID')
                if not durable['matches']:raise RuntimeError('Native ACK has no independently visible committed target record')
                if any(e.get('token')==token and 'provider' in e['kind'] for e in fixture.events):raise RuntimeError('Target reached its worker/provider before the declared pre-dispatch crash boundary')
            old_pid=gateway.process.pid;metadata['fault_started_monotonic_ns']=time.monotonic_ns();os.killpg(old_pid,signal.SIGKILL);gateway.process.wait(timeout=5)
            metadata.update(actual_killed_gateway_pid=old_pid,native_ack=ack,client_ack_received_before_fault=mode=='after-client-ack')
            fixture.wire_release.set();fixture.release.set()
            if blocker:metadata['interrupted_unrelated_slot_owner']=blocker.result(timeout=40)
            if not fixture.client_result.wait(timeout=8):raise RuntimeError('Original native wire did not settle after the actual process crash')
            metadata['original_client_report']=settle(wire);wire=None
        gateway.stop();gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready();wait_control(gateway,fixture,token+'_RESTART_READY')
        deadline=time.monotonic()+(20 if mode!='before-append' else 1)
        while time.monotonic()<deadline and fixture.receipts.get(token,0)==0:time.sleep(.1)
        metadata.update(effects_before_explicit_retry=fixture.receipts.get(token,0),committed_records_after_restart=committed_matches(root,token),
            recovery_observation_deadline_seconds=20 if mode!='before-append' else 1)
        if mode=='before-append':check('unforwarded-unacknowledged-request-is-not-spontaneously-dispatched',fixture.receipts.get(token,0)==0)
        if mode=='after-client-ack':check('acknowledged-durable-queued-work-recovers-within-declared-deadline',fixture.receipts.get(token,0)==1)
        fixture.client_result.clear();wire=launch('retry')
        if not fixture.client_result.wait(timeout=12):raise RuntimeError('Explicit same-identity idempotent retry produced no native RPC result')
        metadata['explicit_operator_retry']=settle(wire);wire=None
        deadline=time.monotonic()+20
        while time.monotonic()<deadline and fixture.receipts.get(token,0)==0:time.sleep(.1)
        check('same-identity-explicit-retry-never-duplicates-target-effect',fixture.receipts.get(token,0)==1)
        check('recovered-native-transcript-retains-target-identity',token in json.dumps(privacy_cases.history(root,session)))
        if any(e['kind']=='admission-wire-gate-timeout' for e in fixture.events):raise RuntimeError('Admission network gate timed out; fault timing is invalid')
        row.update(native_invoked=True,fixture_validated=True,state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,
            native_history=privacy_cases.history(root,session),resources=gateway.sampler.summary(),paid_model_calls=0,
            scope='Native public chat.send with the same persistent synthetic device and idempotency identity. Before-append is a held request before forwarding to native admission, not an invented internal SQLite hook. Held server ACK and actual client-received ACK are separate. SQLite committed visibility is independently read; no raw database writes or runtime patches are used.')
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2500],metadata=metadata)
    finally:
        fixture.wire_release.set();fixture.release.set()
        if wire:
            try:settle(wire)
            except Exception:
                wire.kill();wire.communicate(timeout=5)
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-4000:]
        row.update(independent_wire_events=fixture.wire_events,independent_effects=fixture.receipts,independent_native_provider_events=fixture.events)
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
