"""Native Stop at actual queue, synchronous tool, child and checkpoint boundaries."""
import concurrent.futures
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

from authorization_observation_cases import AuthorizationFixture
from backup_cases import queued_admission
from effect_recovery_cases import wait_control
import harness_contract_cases
from mcp_contract_cases import wait_started
from mcp_http_fixture import McpHTTPFixture
import mechanism_cases
import pilot
import privacy_cases
import service_path_cases as service

SCENARIOS={f'REL-05-S{i:02}':mode for i,mode in enumerate(['queued','synchronous','background-child','checkpointed'],1)}


class CancellationFixture(AuthorizationFixture):
    def __init__(self):
        self.controls=[];self.control_written=threading.Event();self.control_returned=threading.Event()
        self.harness_events=[];self.pause_entered=threading.Event();self.pause_release=threading.Event();self.pause_release.set()
        self.parent_token=None;self.parent_returns=[];self.parent_entered=threading.Event();self.parent_release=threading.Event();self.parent_release.set()
        super().__init__();self.gate_timeout_seconds=30
    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def do_POST(self):
                if self.path in {'/cancellation-control','/harness-event','/harness-pause'}:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=65536:return self.send(dict(error='owned-cancellation-bound'),413)
                    body=json.loads(self.rfile.read(size));body['monotonic_ns']=time.monotonic_ns()
                    if self.path=='/cancellation-control':
                        owner.controls.append(body)
                        if body.get('kind')=='actual-stop-request-written':owner.control_written.set()
                        if body.get('kind')=='actual-stop-response':owner.control_returned.set()
                    elif self.path=='/harness-event':owner.harness_events.append(body)
                    else:
                        owner.harness_events.append(dict(body,kind='actual-checkpoint-process-held'));owner.pause_entered.set()
                        if not owner.pause_release.wait(timeout=20):owner.event('checkpoint-pause-timeout');return self.send(dict(error='pause-timeout'),504)
                    return self.send(dict(observed=True))
                if self.path.endswith('/chat/completions') and owner.parent_token:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=4*1024**2:return self.send(dict(error='bounded-parent-input'),413)
                    raw=self.rfile.read(size);body=json.loads(raw)
                    users=[(i,re.search(r'PILOT_[A-Z0-9_]+',str(m.get('content','')))) for i,m in enumerate(body.get('messages',[])) if m.get('role')=='user']
                    marked=[(i,m.group()) for i,m in users if m];index,token=marked[-1] if marked else (0,None)
                    if token==owner.parent_token and any(m.get('role')=='tool' for m in body['messages'][index+1:]):
                        owner.parent_returns=[m for m in body['messages'][index+1:] if m.get('role')=='tool']
                        owner.event('actual-parent-model-wait',token=token);owner.parent_entered.set()
                        if not owner.parent_release.wait(timeout=20):owner.event('parent-model-gate-timeout');return self.send(dict(error='parent-gate-timeout'),504)
                    original=self.rfile;self.rfile=io.BytesIO(raw)
                    try:return super().do_POST()
                    finally:self.rfile=original
                return super().do_POST()
        return Handler


def configure(root,mode):
    if mode=='checkpointed':return harness_contract_cases.configure(root,'harness')
    config=service.configure(root);config['tools']['allow'].append('sessions_spawn');config['agents']['defaults']['subagents']=dict(maxConcurrent=2,maxSpawnDepth=1)
    if mode=='queued':config['agents']['defaults']['maxConcurrent']=1
    if mode=='background-child':
        config['mcp']=dict(servers=dict(cancelpeer=dict(transport='streamable-http',url='http://127.0.0.1:18085/mcp',requestTimeoutMs=15000,connectionTimeoutMs=5000)))
        config['tools']['allow'].append('cancelpeer__eval_probe')
    if mode=='synchronous':
        path=root/'composition-a/index.js';gate=root/'workspace/synchronous-gate';entered=root/'workspace/synchronous-entered'
        code="if(args.action==='sync-block'){fs.writeFileSync("+json.dumps(str(entered))+",JSON.stringify({pid:process.pid}));const until=Date.now()+5000;while(fs.existsSync("+json.dumps(str(gate))+")&&Date.now()<until){}await announce('work',{sync_gate_timeout:fs.existsSync("+json.dumps(str(gate))+")});}\n"
        path.write_text(path.read_text().replace("if(args.action==='cpu'){",code+"if(args.action==='cpu'){"))
    pilot.save(root/'config.json',config);return config


def alive(pid):
    try:return Path('/proc',str(pid),'stat').read_text().split(') ',1)[1].split()[0]!='Z'
    except (OSError,IndexError):return False


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];token='PILOT_CANCELLATION_'+scenario.replace('-','_')+'_U'+str(unit)
    fixture=CancellationFixture();peer=McpHTTPFixture() if mode=='background-child' else None;gateway=None;control=None;assertions=[];metadata={};requests=[]
    session='agent:main:pilot:'+token.lower();row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['actual-native-stop-ACK-and-policy-state','independent-live-work-queue-or-checkpoint-gates','actual-descendant-processes-effects-and-MCP-cancel-notifications']))
    def operator():
        spec=root/'cancel-operator.json';pilot.save(spec,dict(shared_token=pilot.TOKEN,session_key=session,clear_queued=mode=='queued'))
        child=subprocess.Popen([pilot.NODE,'/driver/cancellation_control.mjs',str(spec)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        first=child.stdout.readline()
        if not first.strip() or not json.loads(first).get('ready'):child.kill();child.communicate(timeout=5);raise RuntimeError('Pre-connected native cancellation operator failed')
        return child
    def stop():
        control.stdin.write('abort\n');control.stdin.flush()
        if not fixture.control_written.wait(timeout=2):raise RuntimeError('Actual Stop request was not written by the pre-connected native operator')
        written=next(r for r in fixture.controls if r['kind']=='actual-stop-request-written')
        if not written.get('written'):raise RuntimeError('Actual Stop request lacks its native socket-write completion')
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:configure(p,mode));gateway.ready();wait_control(gateway,fixture,token+'_CONTROL')
        if peer:
            positive=token+'_MCP_CONTROL';peer.register(positive);fixture.plan(positive,'cancelpeer__eval_probe',dict(token=positive),'RECEIPT:'+positive)
            if not gateway.request(positive)['accepted'] or peer.receipts.get(positive)!=1:raise RuntimeError('Actual native child-tool MCP transport positive control failed')
        if mode=='checkpointed':
            ready=token+'_SESSION_READY';fixture.register(ready)
            if not gateway.request(ready,session_key=token.lower())['accepted']:raise RuntimeError('Actual resumable native session initialization failed')
            selected=privacy_cases.wire(root,[dict(method='sessions.patch',params=dict(key=session,model='fixture/fixture-model',agentRuntime='eval-external-harness',permissionMode='full'))])
            metadata['native_harness_selection']=selected
            if not selected['responses'][0]['result'].get('ok'):raise RuntimeError('Actual checkpoint-capable reference harness selection failed')
        control=operator();row.update(native_invoked=True,fixture_validated=True)
        if mode=='queued':
            blocker=token+'_BLOCKER';fixture.register(blocker,gate=True);fixture.register(token);fixture.release.clear()
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                active=pool.submit(gateway.request,blocker)
                if not mechanism_cases.wait_events(fixture,'effect-start',[blocker],seconds=12):raise RuntimeError('Actual occupied native worker slot was not established')
                pending=pool.submit(gateway.request,token);deadline=time.monotonic()+8;queued={}
                while time.monotonic()<deadline:
                    queued=privacy_cases.history(root,session)
                    if queued_admission(queued,session):break
                    time.sleep(.1)
                if not queued_admission(queued,session):raise RuntimeError('Actual target HTTP request lacks native queued custody')
                metadata['native_queued_custody']=queued;stop()
                if not fixture.control_returned.wait(timeout=5):raise RuntimeError('Native Stop failed to return while target remained queued')
                fixture.release.set();result=pending.result(timeout=40);neighbor=active.result(timeout=40);requests.extend([result,neighbor])
            check('cancelled-queued-request-does-not-dispatch',not result['accepted'] and not fixture.receipts.get(token))
            check('unrelated-running-slot-owner-completes-once',neighbor['accepted'] and fixture.receipts.get(blocker)==1)
        elif mode=='synchronous':
            fixture.register(token,action='sync-block');gate=root/'workspace/synchronous-gate';entered=root/'workspace/synchronous-entered';gate.write_text('hold')
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pending=pool.submit(gateway.request,token);deadline=time.monotonic()+10
                while time.monotonic()<deadline and not entered.exists():time.sleep(.005)
                if not entered.exists():raise RuntimeError('Actual synchronous native plugin code did not enter its independent file gate')
                metadata['synchronous_plugin_pid']=json.loads(entered.read_text())['pid'];stop()
                responded=fixture.control_returned.wait(timeout=.5);metadata['stop_response_before_busy_loop_release']=responded
                check('Stop-is-serviceable-during-declared-synchronous-tool-window',responded)
                metadata['synchronous_gate_release_ns']=time.monotonic_ns();gate.unlink();result=pending.result(timeout=40);requests.append(result)
            if not fixture.control_returned.wait(timeout=5):raise RuntimeError('Native Stop did not settle after the bounded synchronous code returned')
            if any(e.get('sync_gate_timeout') for e in fixture.events):raise RuntimeError('Synchronous work safety deadline expired; timing fixture invalid')
            metadata['synchronous_scope']='The actual trusted native plugin deliberately executes synchronous JavaScript. Stop request write and response are separate; existing effects are not retroactively classified as prevented.'
        elif mode=='background-child':
            child=token+'_CHILD';fixture.child_tokens.add(child);peer.register(child,gate=True);peer.release.clear();fixture.plan(child,'cancelpeer__eval_probe',dict(token=child),'RECEIPT:'+child)
            fixture.parent_token=token;fixture.parent_release.clear();fixture.plan(token,'sessions_spawn',dict(task='Execute the deterministic operation for '+child,mode='run',cleanup='keep',label='owned-cancellation-child'),'childSessionKey')
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pending=pool.submit(gateway.request,token)
                if not fixture.parent_entered.wait(timeout=15) or not wait_started(peer,child):raise RuntimeError('Actual live parent and child MCP work were not both established')
                text=json.dumps(fixture.parent_returns);matches=re.findall(r'agent:[a-z0-9_-]+:subagent:[a-zA-Z0-9-]+',text)
                if not matches:raise RuntimeError('Actual native child session identity was not returned')
                metadata['actual_child_session']=matches[0];stop()
                if not fixture.control_returned.wait(timeout=5):raise RuntimeError('Native active parent Stop did not return')
                peer.release.set();fixture.parent_release.set();result=pending.result(timeout=40);requests.append(result)
            time.sleep(.5)
            check('cancelled-live-parent-is-not-falsely-completed',not result['accepted'])
            check('Stop-propagates-to-real-child-MCP-operation',not peer.receipts.get(child) and any(e['kind']=='mcp-cancel-notification' and e.get('matched') for e in peer.events))
            metadata['native_child_after_stop']=privacy_cases.history(root,matches[0])
        else:
            task=dict(task_id=token,operation='add',left=31,right=47,pause_after_checkpoint=True);fixture.pause_release.clear()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pending=pool.submit(privacy_cases.request,gateway,token,session,'HARNESS_TASK '+json.dumps(task))
                if not fixture.pause_entered.wait(timeout=12):raise RuntimeError('Actual external executor did not persist and reach its checkpoint gate')
                held=next(e for e in fixture.harness_events if e['kind']=='actual-checkpoint-process-held');pid=held['pid']
                if not alive(pid):raise RuntimeError('Checkpointed executor was not actually alive before Stop')
                stop()
                if not fixture.control_returned.wait(timeout=5):raise RuntimeError('Native Stop did not return for the actual resumable executor')
                deadline=time.monotonic()+2
                while time.monotonic()<deadline and alive(pid):time.sleep(.02)
                check('actual-external-descendant-exits-within-two-seconds-after-Stop',not alive(pid))
                fixture.pause_release.set();result=pending.result(timeout=40);requests.append(result)
            check('cancelled-checkpoint-turn-is-not-falsely-completed',not result['accepted'])
            old=gateway.process.pid;gateway.stop();gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready();wait_control(gateway,fixture,token+'_RESTART_READY')
            result=privacy_cases.request(gateway,token+'_CONTINUE',session,'HARNESS_TASK '+json.dumps(task));requests.append(result)
            actual=[e for e in fixture.harness_events if e['kind']=='external-attempt-result' and e.get('task_id')==token]
            check('same-native-session-resumes-owned-checkpoint-on-explicit-continuation',gateway.process.pid!=old and result['accepted'] and bool(actual) and actual[-1]['resumed'] and actual[-1]['value']==78 and actual[-1]['calculation_count']==1)
            metadata['checkpoint_scope']='Public native harness plus its own input-bound pure-arithmetic checkpoint, not a claim that arbitrary native tools automatically checkpoint or roll back effects.'
        responses=[r for r in fixture.controls if r['kind']=='actual-stop-response']
        check('actual-native-stop-RPC-is-acknowledged',bool(responses) and responses[-1]['native_response'].get('ok') is True)
        if any(e['kind'] in {'checkpoint-pause-timeout','parent-model-gate-timeout','fixture-gate-timeout'} for e in fixture.events):raise RuntimeError('Actual cancellation fixture gate timed out')
        if peer and any(e['kind']=='mcp-fixture-gate-timeout' for e in peer.events):raise RuntimeError('Actual child cancellation peer gate timed out')
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,requests=requests,
            native_history=privacy_cases.history(root,session),resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2400],metadata=metadata)
    finally:
        fixture.pause_release.set();fixture.parent_release.set();fixture.release.set()
        if peer:peer.release.set()
        (root/'workspace/synchronous-gate').unlink(missing_ok=True)
        if control:
            try:
                control.stdin.write('finish\n');control.stdin.flush();output,error=control.communicate(timeout=12);row['native_operator_report']=json.loads(output.strip().splitlines()[-1])
            except (OSError,ValueError,IndexError,subprocess.TimeoutExpired) as error:
                control.kill();control.communicate(timeout=5);row.update(state='harness-error',reason='Native stop operator failed to settle: '+str(error)[:300])
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-4000:]
        row.update(independent_stop_events=fixture.controls,independent_events=fixture.events,independent_effects=fixture.receipts,independent_harness_events=fixture.harness_events,
            independent_mcp_events=peer.events if peer else [],independent_mcp_effects=peer.receipts if peer else {})
        if peer:peer.close()
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
