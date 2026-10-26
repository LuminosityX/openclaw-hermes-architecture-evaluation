"""Reconstruct actual approval scope using native exports, then compare held truth."""
import hashlib
import io
import json
import re
import shutil
import subprocess
import threading
import time

from effect_recovery_cases import wait_control
from operation_fixture import OperationFixture
import pilot
import privacy_cases
import recovery_cases
import service_path_cases as service

SCENARIOS={f'OBS-01-S{i:02}':mode for i,mode in enumerate(['single-use','session','persistent','revoked-inherited'],1)}


def reconstruct(native_records):
    """No scenario ID, intervention ledger, expected scope or actor is accepted."""
    nodes=[]
    def visit(value):
        if isinstance(value,dict):
            nodes.append(value)
            for child in value.values():visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    visit(native_records)
    decisions={n.get('decision') for n in nodes if n.get('status') in {'allowed','denied','cancelled','expired'} and isinstance(n.get('decision'),str)}
    modes={n.get('permissionMode') for n in nodes if n.get('permissionMode') in {'full','guarded','workspace','read-only'}}
    parent_links=[n.get(key) for n in nodes for key in ['spawnedBy','parentSessionKey','parentKey'] if isinstance(n.get(key),str) and n[key].startswith('agent:')]
    allowlists=[n['allowlist'] for n in nodes if isinstance(n.get('allowlist'),list) and n['allowlist']]
    choice=('single-use' if 'allow-once' in decisions else 'revoked-inherited' if parent_links and {'full','read-only'}<=modes else 'persistent' if allowlists else 'session' if 'full' in modes else 'unknown')
    actors=[];targets=[];versions=[]
    for node in nodes:
        if choice=='single-use':actor_relevant=node.get('decision')=='allow-once' and node.get('status')=='allowed'
        elif choice=='session':actor_relevant=node.get('permissionMode')=='full'
        elif choice=='persistent':actor_relevant=bool(node.get('allowlist') or isinstance(node.get('file'),dict))
        elif choice=='revoked-inherited':actor_relevant=node.get('permissionMode') in {'full','read-only'}
        else:actor_relevant=False
        if actor_relevant:
            for key in ['resolvedBy','resolver','reviewer','updatedBy']:
                value=node.get(key)
                if value:actors.append(dict(field=key,value=value))
        for key in ['command','commandText','sessionKey','key']:
            value=node.get(key)
            if isinstance(value,str) and value:targets.append(dict(field=key,value=value))
        if isinstance(node.get('hash'),str) and isinstance(node.get('file'),dict):versions.append(node['hash'])
    return dict(authority_choice=choice,actors=actors,targets=targets,policy_versions=sorted(set(versions)),
        parent_links=sorted(set(parent_links)),permission_modes=sorted(modes),terminal_decisions=sorted(decisions),
        scope='Native RPC projections only. Supplied observer/request truth is not used to infer an actor absent from the product records.')


class AuthorizationFixture(OperationFixture):
    def __init__(self):self.held_token=None;self.entered=threading.Event();self.allow_model=threading.Event();self.allow_model.set();super().__init__()
    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def do_POST(self):
                if self.path.endswith('/chat/completions') and owner.held_token:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=4*1024**2:return self.send(dict(error='bounded-model-input'),413)
                    raw=self.rfile.read(size);body=json.loads(raw)
                    users=[str(m.get('content','')) for m in body.get('messages',[]) if m.get('role')=='user']
                    if any(owner.held_token in text for text in users):
                        owner.event('owned-child-model-gate',token=owner.held_token);owner.entered.set();owner.allow_model.wait(timeout=30)
                    original=self.rfile;self.rfile=io.BytesIO(raw)
                    try:return super().do_POST()
                    finally:self.rfile=original
                return super().do_POST()
        return Handler


def configure(root):
    config=service.configure(root);config['tools']['allow'].extend(['exec','sessions_spawn'])
    config['tools']['exec']=dict(host='gateway',mode='ask')
    config['gateway']['controlUi'].update(enabled=True,allowedOrigins=['http://127.0.0.1:18789'])
    config['agents']['defaults']['subagents']=dict(maxConcurrent=2,maxSpawnDepth=1)
    pilot.save(root/'config.json',config);return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];token='PILOT_AUTHORIZATION_'+scenario.replace('-','_')+'_U'+str(unit)
    session='agent:main:pilot:'+token.lower();fixture=AuthorizationFixture();gateway=None;observer=None;assertions=[];metadata={};records=[];requests=[]
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-terminal-approval-history','native-permission-and-policy-snapshots','independent-owned-effect-and-grant-timeline']))
    def wire(operations):
        result=privacy_cases.wire(root,operations);records.extend(result['responses']);return result
    def patch(key,value):
        result=wire([dict(method='sessions.patch',params=dict(key=key,permissionMode=value))])['responses'][0]['result']
        if not result.get('ok'):raise RuntimeError('Native permission-mode change failed: '+json.dumps(result)[:1400])
        return result
    def observe():
        spec=root/'approval-observer.json';pilot.save(spec,dict(shared_token=pilot.TOKEN,command_marker=str(script),effect_path=str(effect),decision='allow-once' if mode=='single-use' else 'deny'))
        process=subprocess.Popen([pilot.NODE,'/driver/approval_observer.mjs',str(spec)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        first=process.stdout.readline()
        if not first.strip() or not json.loads(first).get('ready'):raise RuntimeError('Native authorization observer failed to become ready: '+first[:1000])
        return process
    def execute(item,key=None):
        fixture.plan(item,'exec',dict(command='python3 '+str(script)+' '+item,yieldMs=10000),'RECEIPT:'+item)
        result=gateway.request(item,session_key=key or token.lower());requests.append(result);return result
    try:
        gateway=pilot.Gateway(root,configurer=configure);gateway.ready()
        control=token+'_CONTROL';fixture.register(control)
        positive=gateway.request(control,session_key=token.lower())
        if not positive['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Native authorization baseline control failed')
        row.update(native_invoked=True,fixture_validated=True)
        script=root/'workspace/owned-authorization-work.py';effect=root/'workspace/owned-authorization-effect'
        script.write_text('from pathlib import Path\nfrom urllib.request import Request,urlopen\nimport json,sys\n'
            'token=sys.argv[1]\nwith Path('+repr(str(effect))+').open("a") as f:f.write(token+"\\n")\n'
            'with urlopen(Request("http://127.0.0.1:18080/effect",data=json.dumps(dict(token=token)).encode(),headers={"Content-Type":"application/json"}),timeout=5) as r:print(r.read().decode())\n')
        before=wire([dict(method='exec.approvals.get',params={}),dict(method='sessions.get',params=dict(key=session))])
        observer=observe();before_boundary=time.monotonic_ns()
        if mode=='single-use':
            item=token+'_ACTION';result=execute(item)
            if not result['accepted'] or fixture.receipts.get(item)!=1:raise RuntimeError('Actual human-approved command control failed')
        elif mode=='session':
            patch(session,'full');item=token+'_SESSION_ACTION';result=execute(item)
            check('session-authorized-command-actually-runs',result['accepted'] and fixture.receipts.get(item)==1)
        elif mode=='persistent':
            snapshot=before['responses'][0]['result']
            if not snapshot.get('ok') or not isinstance(snapshot.get('payload'),dict):raise RuntimeError('Native policy read control failed')
            old=snapshot['payload'];policy=dict(version=1,defaults=dict(security='allowlist',ask='on-miss'),agents=dict(main=dict(allowlist=[dict(pattern=str(__import__('pathlib').Path('/usr/bin/python3').resolve()))])))
            set_result=wire([dict(method='exec.approvals.set',params=dict(file=policy,baseHash=old['hash']))])['responses'][0]['result']
            if not set_result.get('ok'):raise RuntimeError('Native persistent policy grant failed: '+json.dumps(set_result)[:1000])
            item=token+'_PERSISTENT_ACTION';result=execute(item)
            if not result['accepted'] or fixture.receipts.get(item)!=1:raise RuntimeError('Native manual persistent grant did not admit its command; calibration incomplete')
            check('persistent-grant-actually-admits-owned-command',True)
            gateway.stop();gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready();wait_control(gateway,fixture,token+'_RESTART_CONTROL')
            if observer:observer.stdin.write('finish\n');observer.stdin.flush();output,error=observer.communicate(timeout=15);old_observation=json.loads(output.strip().splitlines()[-1]);records.append(dict(result=dict(ok=True,payload=old_observation.get('native_history',{}).get('payload'))));metadata['pre_restart_observer']=old_observation;observer=None
            observer=observe();second=token+'_AFTER_RESTART';continued=execute(second)
            check('persistent-grant-survives-native-restart',continued['accepted'] and fixture.receipts.get(second)==1)
        else:
            patch(session,'full')
            def spawn(child,label):
                fixture.plan(child,'exec',dict(command='python3 '+str(script)+' '+child,yieldMs=10000),'RECEIPT:'+child)
                parent=token+'_'+label;fixture.plan(parent,'sessions_spawn',dict(task='Execute the deterministic operation for '+child,mode='run',cleanup='keep',label='owned-authorization-child'),'childSessionKey')
                deadline=time.monotonic()+30
                while True:
                    prior=set(gateway.log_tail);result=gateway.request(parent,session_key=token.lower());requests.append(result)
                    seen=any(e.get('token')==parent and 'provider' in e['kind'] for e in fixture.events)
                    fresh=''.join(line for line in gateway.log_tail if line not in prior)
                    if not recovery_cases.pending_admission(result,fresh,seen,fixture.receipts.get(parent,0)) or time.monotonic()>=deadline:break
                    time.sleep(.5)
                metadata.setdefault('actual_spawn_attempts',[]).append(dict(parent=parent,response=result,tool_returns=fixture.tool_returns.get(parent,[]),
                    matching_native_provider_events=[e for e in fixture.events if e.get('token')==parent][-6:]))
                text=json.dumps(fixture.tool_returns.get(parent,[]));keys=re.findall(r'agent:[a-z0-9_-]+:subagent:[a-zA-Z0-9-]+',text)
                if not keys:raise RuntimeError('Native child grant probe returned no child identity: '+json.dumps(metadata['actual_spawn_attempts'][-1])[:1800])
                return keys[0]
            baseline_child=token+'_BASE_CHILD';baseline_key=spawn(baseline_child,'BASE_SPAWN')
            deadline=time.monotonic()+25
            while time.monotonic()<deadline and fixture.receipts.get(baseline_child)!=1:time.sleep(.1)
            if fixture.receipts.get(baseline_child)!=1:raise RuntimeError('Inherited full-mode child exec positive control failed')
            child=token+'_HELD_CHILD';fixture.held_token=child;fixture.allow_model.clear();child_key=spawn(child,'HELD_SPAWN')
            if not fixture.entered.wait(timeout=15):raise RuntimeError('Actual child model/tool dispatch gate was not reached')
            wire([dict(method='sessions.get',params=dict(key=child_key)),dict(method='sessions.get',params=dict(key=session))])
            revoked=patch(session,'read-only');metadata['revocation_monotonic_ns']=time.monotonic_ns();fixture.allow_model.set()
            deadline=time.monotonic()+20
            while time.monotonic()<deadline and not fixture.tool_returns.get(child):time.sleep(.1)
            wire([dict(method='sessions.get',params=dict(key=child_key)),dict(method='sessions.get',params=dict(key=session))])
            metadata.update(child_session=child_key,baseline_child_session=baseline_key,post_parent_revocation_child_effects=fixture.receipts.get(child,0),
                revocation_scope='Actual parent session mode tightened after the inherited child was spawned and while its model response was held before tool dispatch. Child current authority is observed, not assumed to be recursively revoked by an undocumented guarantee.')
        wire([dict(method='exec.approvals.get',params={}),dict(method='sessions.get',params=dict(key=session)),dict(method='chat.history',params=dict(sessionKey=session,limit=50,maxBytes=131072,toolResultMaxChars=8000))])
        observer.stdin.write('finish\n');observer.stdin.flush();output,error=observer.communicate(timeout=20)
        observed=json.loads(output.strip().splitlines()[-1]);observer=None
        if observed.get('harness_error'):raise RuntimeError('Native approval observer failed: '+json.dumps(observed)[:1000])
        # Only native projections go to the blind reconstructor. Client-selected
        # decision and held actor/scope truth stay in separate grading metadata.
        native=dict(rpc_responses=records,terminal_history=observed.get('native_history'),
            approval_native_projections=[dict(terminal=a.get('native_terminal'),exec_projection=a.get('native_exec_projection'),request=a.get('native_requested_event')) for a in observed['approvals']])
        diagnosed=reconstruct(native)
        check('native-records-identify-the-actual-authority-choice',diagnosed['authority_choice']==mode)
        check('native-records-identify-authorization-actor',bool(diagnosed['actors']))
        check('native-records-retain-target-and-policy-version',bool(diagnosed['targets']) and bool(diagnosed['policy_versions']))
        metadata.update(diagnosis=diagnosed,truth_scope=mode,truth_reviewer_device=observed.get('reviewer_device_id'),
            grant_boundary_monotonic_ns=before_boundary,observer=observed,
            method='Frozen native-field reconstructor, no scenario label or expected scope input. Missing actors remain unknown; no human usability or policy violation claim is inferred.')
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,native_records=native,
            requests=requests,independent_events=fixture.events,independent_receipts=fixture.receipts,resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2400],metadata=metadata)
    finally:
        fixture.allow_model.set()
        if observer:
            if observer.poll() is None:observer.terminate()
            try:observer.communicate(timeout=3)
            except subprocess.TimeoutExpired:observer.kill();observer.communicate()
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-3500:]
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
