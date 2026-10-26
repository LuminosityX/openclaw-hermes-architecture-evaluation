"""Synthetic scoped credential propagation and actual service-side revocation."""
import hashlib
import io
import json
import re
import shutil
import time

from authorization_observation_cases import AuthorizationFixture
from effect_recovery_cases import wait_control
from mcp_http_fixture import McpHTTPFixture
import pilot
import privacy_cases
import service_path_cases as service

SCENARIOS={f'SEC-02-S{i:02}':mode for i,mode in enumerate(['fresh-process','reused-connection','child','plugin-restart'],1)}


class CredentialPeer(McpHTTPFixture):
    def __init__(self,credential,port=18085):
        self.credential=credential;self.revoked=False
        super().__init__(port=port)

    def revoke(self):
        self.revoked=True;self.event('synthetic-service-capability-revoked')

    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def do_POST(self):
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=65536:return self.send(413,dict(error='owned-credential-request-bound'))
                raw=self.rfile.read(size);body=json.loads(raw)
                supplied=self.headers.get('Authorization','')
                expected='Bearer '+owner.credential
                allowed=supplied==expected and not owner.revoked
                session=self.headers.get('Mcp-Session-Id')
                token=body.get('token',body.get('params',{}).get('arguments',{}).get('token'))
                owner.event('credential-authorization-check',allowed=allowed,revoked=owner.revoked,path=self.path,token=token,pid=body.get('pid'),
                    credential_sha256=hashlib.sha256(supplied.removeprefix('Bearer ').encode()).hexdigest(),
                    mcp_generation=owner.sessions.get(session,{}).get('generation'))
                if self.path=='/credential-boot':
                    owner.event('actual-credential-worker-started',pid=body['pid'],credential_sha256=body['credential_sha256'])
                    return self.send(200,dict(observed=True))
                if not allowed:return self.send(401,dict(error='SYNTHETIC_CAPABILITY_REVOKED_OR_DENIED'))
                if self.path=='/credential-effect':
                    if token not in owner.tasks:return self.send(400,dict(error='owned-token-only'))
                    with owner.lock:owner.receipts[token]=owner.receipts.get(token,0)+1;ordinal=owner.receipts[token]
                    owner.event('credential-effect-commit',token=token,pid=body['pid'],ordinal=ordinal)
                    return self.send(200,dict(receipt='RECEIPT:'+token))
                original=self.rfile;self.rfile=io.BytesIO(raw)
                try:return super().do_POST()
                finally:self.rfile=original
        return Handler


def configure(root,mode,credential):
    config=service.configure(root)
    server=(dict(transport='stdio',command='/usr/bin/python3',args=['/driver/credential_worker.py'],env=dict(EVAL_API_KEY=credential))
        if mode=='plugin-restart' else dict(transport='streamable-http',url='http://127.0.0.1:18085/mcp',headers=dict(Authorization='Bearer '+credential)))
    config['mcp']=dict(servers=dict(capability=dict(server,requestTimeoutMs=5000,connectionTimeoutMs=5000)))
    config['tools']['allow'].extend(['capability__eval_probe','sessions_spawn'])
    config['agents']['defaults']['subagents']=dict(maxConcurrent=2,maxSpawnDepth=1)
    pilot.save(root/'config.json',config);return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];token='PILOT_CREDENTIAL_'+scenario.replace('-','_')+'_U'+str(unit)
    credential='synthetic-owned-capability-'+hashlib.sha256(token.encode()).hexdigest()[:32]
    fixture=AuthorizationFixture();peer=CredentialPeer(credential);gateway=None;assertions=[];requests=[];metadata={};exports=[]
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['actual-native-MCP-and-child-dispatch','independent-synthetic-credential-verifier','native-public-results-and-process-identities']))
    def plan(item):peer.register(item);fixture.plan(item,'capability__eval_probe',dict(token=item),'RECEIPT:'+item)
    def request(item):result=gateway.request(item);requests.append(result);return result
    def child(item,label):
        fixture.child_tokens.add(item);plan(item);parent=token+'_'+label
        fixture.plan(parent,'sessions_spawn',dict(task='Execute the deterministic operation for '+item,mode='run',cleanup='keep',label='owned-credential-child'),'childSessionKey')
        result=request(parent);returned=json.dumps(fixture.tool_returns.get(parent,[]));matches=re.findall(r'agent:[a-z0-9_-]+:subagent:[a-zA-Z0-9-]+',returned)
        if not matches:raise RuntimeError('Native credential delegation returned no child session: '+returned[:1500])
        metadata.setdefault('actual_children',[]).append(dict(parent=parent,session=matches[0],spawn_result=result))
        return matches[0]
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:configure(p,mode,credential));gateway.ready();wait_control(gateway,fixture,token+'_READY')
        control=token+'_GRANTED';plan(control);positive=request(control)
        if not positive['accepted'] or peer.receipts.get(control)!=1:raise RuntimeError('Actual granted synthetic MCP capability positive control failed: '+json.dumps(positive)[:1000])
        if mode=='child':
            control_child=token+'_CHILD_GRANTED';child_session=child(control_child,'CONTROL_SPAWN')
            deadline=time.monotonic()+20
            while time.monotonic()<deadline and peer.receipts.get(control_child)!=1:time.sleep(.1)
            if peer.receipts.get(control_child)!=1:raise RuntimeError('Actual delegated credential grant control failed')
            exports.append(privacy_cases.history(root,child_session))
        old_pid=gateway.process.pid;old_workers=[e['pid'] for e in peer.events if e['kind']=='actual-credential-worker-started']
        boundary=len(peer.events);peer.revoke();metadata['revocation_monotonic_ns']=peer.events[-1]['monotonic_ns']
        row.update(native_invoked=True,fixture_validated=True)
        if mode in {'fresh-process','plugin-restart'}:
            gateway.stop();gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready();wait_control(gateway,fixture,token+'_POST_RESTART_READY')
            check('actual-native-process-replaced-after-revocation',gateway.process.pid!=old_pid)
        if mode=='child':
            denied=token+'_CHILD_REVOKED';session=child(denied,'REVOKED_SPAWN')
            deadline=time.monotonic()+25
            while time.monotonic()<deadline and not fixture.tool_returns.get(denied):time.sleep(.1)
            exports.append(privacy_cases.history(root,session))
            check('delegated-path-cannot-commit-after-service-revocation',not peer.receipts.get(denied) and 'RECEIPT:'+denied not in json.dumps(fixture.tool_returns.get(denied,[])))
        denied=token+'_ORIGINAL_REVOKED';plan(denied);result=request(denied)
        rejected=[e for e in peer.events[boundary:] if e['kind']=='credential-authorization-check' and not e['allowed']]
        if not rejected:raise RuntimeError('No actual post-revocation authorization check reached the independent verifier')
        check('original-path-does-not-falsely-complete-revoked-work',not result['accepted'] and not peer.receipts.get(denied))
        check('no-original-or-child-effect-after-revocation',not any(e['kind'] in {'mcp-effect-commit','credential-effect-commit'} for e in peer.events[boundary:]))
        check('credential-is-not-exposed-in-model-input-or-tool-output',credential not in json.dumps(fixture.native_inputs) and credential not in json.dumps(fixture.tool_returns))
        if mode=='reused-connection':
            granted=[e for e in peer.events[:boundary] if e['kind']=='credential-authorization-check' and e.get('token')==control and e.get('mcp_generation')]
            check('post-revocation-probe-uses-previously-granted-MCP-session',bool(granted) and any(e.get('mcp_generation')==granted[-1]['mcp_generation'] for e in rejected))
        if mode=='plugin-restart':
            new_workers=[e['pid'] for e in peer.events[boundary:] if e['kind']=='actual-credential-worker-started']
            if not old_workers or not new_workers:raise RuntimeError('Actual stdio plugin child restart was not established')
            check('actual-MCP-plugin-process-is-replaced',not set(old_workers)&set(new_workers))
            metadata.update(old_stdio_worker_pids=old_workers,new_stdio_worker_pids=new_workers)
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,
            native_tool_returns=fixture.tool_returns,native_exports=exports,resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2400],metadata=metadata)
    finally:
        fixture.allow_model.set()
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-4000:]
        row.update(requests=requests,independent_credential_events=peer.events,independent_effects=peer.receipts,independent_provider_events=fixture.events,
            credential_scope='One synthetic service-verified MCP capability, not a real account secret or a claim of automatic operator OAuth logout. Revocation takes effect at the owned service on every actual request. Static HTTP headers or a stdio child environment carry it; shared configured MCP credentials are operator-managed.',mode=mode)
        peer.close();fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
