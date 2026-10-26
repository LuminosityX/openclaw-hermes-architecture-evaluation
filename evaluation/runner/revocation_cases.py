"""Revoke real native session authority at independently proven dispatch gates."""
import concurrent.futures
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

from authorization_observation_cases import AuthorizationFixture,configure as approval_configure,reconstruct
from backup_cases import queued_admission
from effect_recovery_cases import wait_control
import mechanism_cases
from owned_open_gate import OwnedOpenGate
import pilot
import privacy_cases

SCENARIOS={f'SEC-06-S{i:02}':mode for i,mode in enumerate(['single-use','session','delegated','queued'],1)}


def environment_selfcheck():
    path=pilot.BASE/'owned-inode-gate-selfcheck';path.write_text('owned gate control')
    child=subprocess.Popen(['/usr/bin/python3','-c','import sys;sys.stdin.readline();print(open(sys.argv[1]).read())',str(path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    gate=None
    try:
        gate=OwnedOpenGate(path,child.pid);gate.arm();child.stdin.write('read\n');child.stdin.flush()
        if not gate.entered.wait(timeout=4) or child.poll() is not None:raise RuntimeError('Actual inode permission gate failed to hold its exact owned opener')
        gate.release();output,error=child.communicate(timeout=5)
        if child.returncode or output.strip()!='owned gate control':raise RuntimeError('Actual inode gate release did not preserve the original file read')
        return dict(kernel_permission_gate=True,held_pid=child.pid,actual_events=gate.events,scope='Only one owned inode and its exact target process; no native files or source are changed')
    finally:
        if gate:gate.close()
        if child.poll() is None:child.kill();child.wait(timeout=5)
        path.unlink(missing_ok=True)


class RevocationFixture(AuthorizationFixture):
    def __init__(self):
        self.hook_entered=threading.Event();self.hook_release=threading.Event();self.hook_release.set()
        self.decision_returned=threading.Event();self.observations=[];self.file_gate=None
        super().__init__()
    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def do_POST(self):
                if self.path not in {'/revocation-hook','/revocation-observer'}:return super().do_POST()
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=65536:return self.send(dict(error='owned-revocation-bound'),413)
                body=json.loads(self.rfile.read(size));body['monotonic_ns']=time.monotonic_ns();owner.observations.append(body)
                if self.path=='/revocation-hook':
                    owner.hook_entered.set()
                    if not owner.hook_release.wait(timeout=15):owner.event('revocation-hook-gate-timeout');return self.send(dict(error='gate-timeout'),504)
                elif body.get('kind')=='arm-before-native-decision':owner.file_gate.arm()
                elif body.get('kind')=='actual-native-decision-returned':owner.decision_returned.set()
                return self.send(dict(observed=True))
        return Handler


def configure(root,mode):
    config=approval_configure(root);config['tools']['allow'].append('read')
    if mode=='queued':config['agents']['defaults']['maxConcurrent']=1
    if mode in {'session','delegated'}:
        path=root/'composition-a/index.js'
        path.write_text(path.read_text().replace(' const owner="composition-a";',
            ' const owner="composition-a";\n'+
            " api.on('before_tool_call',async(event,ctx)=>{if(event.toolName!=='exec'||!String(event.params?.command).includes('_ACTION'))return;const r=await fetch('http://127.0.0.1:18080/revocation-hook',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'actual-before-tool-call',tool_name:event.toolName,params:event.params,session_key:ctx.sessionKey,run_id:ctx.runId})});if(!r.ok)throw new Error('OWNED_REVOCATION_GATE_FAILURE');});"))
    (root/'workspace/public-after-revocation.txt').write_text('OWNED_PUBLIC_READ')
    pilot.save(root/'config.json',config);return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];token='PILOT_REVOKE_'+scenario.replace('-','_')+'_U'+str(unit)
    fixture=RevocationFixture();fixture.gate_timeout_seconds=30;gateway=None;observer=None;gate=None;requests=[];records=[];assertions=[];metadata={}
    key=token.lower();session='agent:main:pilot:'+key
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def patch(selected,value):
        result=privacy_cases.wire(root,[dict(method='sessions.patch',params=dict(key=selected,permissionMode=value)),dict(method='sessions.get',params=dict(key=selected))]);records.append(result)
        if not result['responses'][0]['result'].get('ok'):raise RuntimeError('Native live permission change failed: '+json.dumps(result)[:1200])
        return result
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['actual-native-grant-and-revocation-records','independent-inode-hook-or-queue-boundary','independent-owned-effects']))
    def plan(item):fixture.plan(item,'exec',dict(command=str(script)+' '+item,yieldMs=10000),'RECEIPT:'+item)
    def request(item,selected=None):result=gateway.request(item,session_key=selected or key);requests.append(result);return result
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:configure(p,mode),drop_capabilities=True);gateway.ready()
        capability_fields={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in Path('/proc',str(gateway.process.pid),'status').read_text().splitlines() if line.startswith(('CapEff:','CapPrm:','CapBnd:','CapAmb:'))}
        if not capability_fields or any(int(value,16) for value in capability_fields.values()):raise RuntimeError('Native Gateway retained evaluator kernel-gate capabilities')
        metadata['native_gateway_capabilities']=capability_fields
        wait_control(gateway,fixture,token+'_READY');control=token+'_SESSION_READY';fixture.register(control)
        if not request(control)['accepted']:raise RuntimeError('Native revocation target initialization failed')
        script=root/'workspace/owned-revocable-command';effect=root/'workspace/actual-command-effects'
        script.write_text('#!/usr/bin/python3\nimport sys,json,os\nfrom pathlib import Path\nfrom urllib.request import Request,urlopen\ntoken=sys.argv[1]\n'
            'with Path('+repr(str(effect))+').open("a") as f:f.write(token+"\\n")\n'
            'with urlopen(Request("http://127.0.0.1:18080/effect",data=json.dumps(dict(token=token,pid=os.getpid())).encode(),headers={"Content-Type":"application/json"}),timeout=5) as r:print(r.read().decode())\n');script.chmod(0o755)
        patch(session,'full');positive=token+'_EXEC_CONTROL';plan(positive)
        if not request(positive)['accepted'] or fixture.receipts.get(positive)!=1:raise RuntimeError('Actual native executable full-mode positive control failed')
        target=token+'_ACTION';plan(target);row.update(native_invoked=True,fixture_validated=True)
        if mode=='single-use':
            patch(session,'guarded');gate=OwnedOpenGate(script,gateway.process.pid);fixture.file_gate=gate
            spec=root/'revocation-observer.json';pilot.save(spec,dict(shared_token=pilot.TOKEN,command_marker=str(script)))
            observer=subprocess.Popen([pilot.NODE,'/driver/revocation_observer.mjs',str(spec)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            if not json.loads(observer.stdout.readline()).get('ready'):raise RuntimeError('Native single-use approval observer failed to initialize')
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pending=pool.submit(request,target)
                if not gate.entered.wait(timeout=14):raise RuntimeError('No actual post-approval Gateway file open reached the pre-launch permission gate')
                if not fixture.decision_returned.wait(timeout=3):raise RuntimeError('The native allow-once decision was not confirmed while the exact Gateway opener was held')
                decisions=[r for r in fixture.observations if r.get('kind')=='actual-native-decision-returned']
                if not decisions or not decisions[-1].get('resolution',{}).get('ok') or reconstruct([decisions[-1].get('terminal'),decisions[-1].get('execProjection')])['authority_choice']!='single-use':
                    raise RuntimeError('The real native terminal approval does not prove an allow-once grant before revocation')
                metadata['pending_before_revocation']=not pending.done();metadata['revocation']=patch(session,'read-only')
                metadata['revocation_ack_monotonic_ns']=time.monotonic_ns();gate.release();result=pending.result(timeout=40)
            check('single-use-grant-and-pre-launch-Gateway-open-were-observed',metadata['pending_before_revocation'] and fixture.decision_returned.is_set())
        elif mode=='session':
            fixture.hook_release.clear()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pending=pool.submit(request,target)
                if not fixture.hook_entered.wait(timeout=12):raise RuntimeError('Actual previously authorized session tool call did not reach its dispatch gate')
                metadata['revocation']=patch(session,'read-only');metadata['revocation_ack_monotonic_ns']=time.monotonic_ns();fixture.hook_release.set();result=pending.result(timeout=40)
        elif mode=='delegated':
            baseline=token+'_BASE_CHILD';fixture.child_tokens.add(baseline);plan(baseline)
            parent_control=token+'_BASE_SPAWN';fixture.plan(parent_control,'sessions_spawn',dict(task='Execute the deterministic operation for '+baseline,mode='run',cleanup='keep',label='owned-delegation-grant-control'),'childSessionKey')
            request(parent_control);deadline=time.monotonic()+20
            while time.monotonic()<deadline and fixture.receipts.get(baseline)!=1:time.sleep(.1)
            if fixture.receipts.get(baseline)!=1:raise RuntimeError('Actual inherited child command grant positive control failed')
            # Keep asynchronous baseline child notifications in the old parent.
            key=token.lower()+'_measured_parent';session='agent:main:pilot:'+key
            parent_ready=token+'_MEASURED_PARENT_READY';fixture.register(parent_ready)
            if not request(parent_ready)['accepted']:raise RuntimeError('Fresh measured parent initialization failed')
            patch(session,'full')
            fixture.hook_release.clear();fixture.child_tokens.add(target)
            parent=token+'_SPAWN';fixture.plan(parent,'sessions_spawn',dict(task='Execute the deterministic operation for '+target,mode='run',cleanup='keep',label='owned-revocable-child'),'childSessionKey')
            result=request(parent);text=json.dumps(fixture.tool_returns.get(parent,[]));matches=re.findall(r'agent:[a-z0-9_-]+:subagent:[a-zA-Z0-9-]+',text)
            if not matches or not fixture.hook_entered.wait(timeout=15):raise RuntimeError('Actual delegated exec did not reach the pre-dispatch gate')
            metadata['child_session']=matches[0];records.append(privacy_cases.wire(root,[dict(method='sessions.get',params=dict(key=matches[0]))]))
            metadata['revocation']=patch(session,'read-only');metadata['revocation_ack_monotonic_ns']=time.monotonic_ns();fixture.hook_release.set()
            deadline=time.monotonic()+20
            while time.monotonic()<deadline and not fixture.tool_returns.get(target):time.sleep(.1)
            result=dict(accepted='RECEIPT:'+target in json.dumps(fixture.tool_returns.get(target,[])))
            metadata['delegation_scope']='Revoke the original parent grant while its actually inherited child call is held before dispatch. Independent child policy is recorded; no recursive live-revocation promise is assumed.'
        else:
            blocker=token+'_BLOCKER';fixture.register(blocker,gate=True);fixture.release.clear()
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                active=pool.submit(gateway.request,blocker)
                if not mechanism_cases.wait_events(fixture,'effect-start',[blocker],seconds=12):raise RuntimeError('Actual occupied native worker slot was not established')
                pending=pool.submit(request,target);deadline=time.monotonic()+8;queued=None
                while time.monotonic()<deadline:
                    queued=privacy_cases.history(root,session)
                    if queued_admission(queued,session):break
                    time.sleep(.1)
                if not queued_admission(queued,session):raise RuntimeError('Target request lacks actual native queued custody before revocation')
                metadata['native_queued_custody']=queued;metadata['revocation']=patch(session,'read-only');metadata['revocation_ack_monotonic_ns']=time.monotonic_ns();fixture.release.set()
                result=pending.result(timeout=40);blocker_result=active.result(timeout=40)
            check('unrelated-already-running-task-continues',blocker_result['accepted'] and fixture.receipts.get(blocker)==1)
        check('revoked-authority-does-not-create-a-post-revocation-effect',not fixture.receipts.get(target))
        check('revoked-action-is-not-falsely-completed',not result['accepted'])
        if gate and any(e['kind']=='owned-inode-gate-timeout' for e in gate.events):raise RuntimeError('Kernel permission gate timed out; timing fixture invalid')
        if any(e['kind']=='revocation-hook-gate-timeout' for e in fixture.events):raise RuntimeError('Public hook gate timed out; timing fixture invalid')
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,native_records=records,native_tool_returns=fixture.tool_returns,
            native_history=privacy_cases.history(root,metadata.get('child_session',session)),resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2400],metadata=metadata,native_records=records)
    finally:
        fixture.hook_release.set();fixture.release.set()
        if gate:gate.close();row['independent_kernel_gate_events']=gate.events
        if observer:
            try:
                observer.stdin.write('finish\n');observer.stdin.flush();output,error=observer.communicate(timeout=12)
                row['native_approval_observer']=json.loads(output.strip().splitlines()[-1])
            except (OSError,ValueError,IndexError,subprocess.TimeoutExpired) as error:
                observer.kill();observer.communicate(timeout=5);row.update(state='harness-error',reason='Native approval observer did not settle: '+str(error)[:300])
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-4000:]
        row.update(requests=requests,independent_boundary_observations=fixture.observations,independent_events=fixture.events,independent_effects=fixture.receipts)
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
