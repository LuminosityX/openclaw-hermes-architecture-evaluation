"""Actual per-session native permissions across shared execution and result reuse."""
import concurrent.futures
import hashlib
import json
import shutil
import threading
import time

from authorization_observation_cases import configure as approval_configure
from effect_recovery_cases import wait_control
from mcp_http_fixture import McpHTTPFixture
from operation_fixture import OperationFixture
import pilot
import privacy_cases
import service_path_cases as service

SCENARIOS={f'SEC-04-S{i:02}':mode for i,mode in enumerate(['sequential','concurrent','cached-result','restart'],1)}


class AuthorityFixture(OperationFixture):
    def __init__(self):
        self.entered=threading.Event();self.allow_effect=threading.Event();self.allow_effect.set()
        super().__init__()

    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def do_POST(self):
                if self.path!='/authority-gate':return super().do_POST()
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4096:return self.send(dict(error='bounded-gate'),413)
                body=json.loads(self.rfile.read(size))
                if body.get('token') not in owner.tasks:return self.send(dict(error='owned-task-only'),403)
                owner.event('owned-authority-gate-entered',**body);owner.entered.set()
                if not owner.allow_effect.wait(timeout=25):
                    owner.event('authority-gate-timeout',**body);return self.send(dict(error='gate-timeout'),504)
                owner.event('owned-authority-gate-released',**body)
                return self.send(dict(released=True))
        return Handler


class CachedAuthorityPeer(McpHTTPFixture):
    """A real externally cached result, not a claimed native internal cache."""
    def __init__(self,canary,port=18085):
        self.canary=canary;self.cached=None;super().__init__(port=port)

    def response(self,body,session_id):
        if body.get('method')=='tools/list':
            result=super().response(body,session_id)
            result['result']['tools'][0]['annotations']=dict(readOnlyHint=False,destructiveHint=True)
            return result
        if body.get('method')=='tools/call':
            if self.cached is not None:
                token=body.get('params',{}).get('arguments',{}).get('token')
                self.event('owned-cached-result-served',token=token,generation=self.sessions[session_id]['generation'])
                return dict(jsonrpc='2.0',id=body['id'],result=self.cached)
            result=super().response(body,session_id)
            if result.get('result',{}).get('content'):
                result['result']['content'].append(dict(type='text',text=self.canary))
                self.cached=result['result'];self.event('owned-result-cache-populated')
            return result
        return super().response(body,session_id)


def configure(root,mode,canary):
    config=approval_configure(root);config['tools']['allow'].append('read')
    (root/'workspace/public-neighbor.txt').write_text('OWNED_PUBLIC_NEIGHBOR')
    (root/'workspace/private-authority.txt').write_text(canary)
    # This observer records the real in-process plugin host; it does not create
    # or claim a separate plugin worker process.
    source=root/'composition-a/index.js'
    source.write_text(source.read_text().replace(' const owner="composition-a";',
        ' const owner="composition-a";\n'+
        " fs.appendFileSync("+json.dumps(str(root/'workspace/plugin-host-boots.jsonl'))+
        ",JSON.stringify({pid:process.pid,at:Date.now()})+'\\n');"))
    if mode=='cached-result':
        config['mcp']=dict(servers=dict(authority=dict(transport='streamable-http',url='http://127.0.0.1:18085/mcp',requestTimeoutMs=5000,connectionTimeoutMs=5000)))
        config['tools']['allow'].append('authority__eval_probe')
    pilot.save(root/'config.json',config);return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];token='PILOT_AUTHORITY_'+scenario.replace('-','_')+'_U'+str(unit)
    canary='OWNED_AUTHORITY_CANARY_'+hashlib.sha256(token.encode()).hexdigest()[:24]
    fixture=AuthorityFixture();peer=None;gateway=None;requests=[];records=[];assertions=[];metadata={}
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    keys={name:token.lower()+'_'+name for name in ['privileged','restricted']}
    def session(name):return 'agent:main:pilot:'+keys[name]
    def patch(name,value):
        result=privacy_cases.wire(root,[dict(method='sessions.patch',params=dict(key=session(name),permissionMode=value)),dict(method='sessions.get',params=dict(key=session(name)))])
        records.append(result)
        if not result['responses'][0]['result'].get('ok'):raise RuntimeError('Native session permission patch failed')
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-per-session-policy-and-tool-results','independent-owned-effect-cache-and-process-records','actual-native-provider-input']))
    def execute(item,name,command):
        fixture.plan(item,'exec',dict(command=command,yieldMs=10000),'RECEIPT:'+item)
        result=gateway.request(item,session_key=keys[name]);requests.append(result);return result
    try:
        if mode=='cached-result':peer=CachedAuthorityPeer(canary)
        gateway=pilot.Gateway(root,configurer=lambda p:configure(p,mode,canary));gateway.ready()
        wait_control(gateway,fixture,token+'_READY')
        script=root/'workspace/owned-authority-command.py'
        script.write_text('import os,sys,json\nfrom pathlib import Path\nfrom urllib.request import Request,urlopen\n'
            'token=sys.argv[1]\n'
            'def post(path):\n with urlopen(Request("http://127.0.0.1:18080/"+path,data=json.dumps(dict(token=token,pid=os.getpid())).encode(),headers={"Content-Type":"application/json"}),timeout=28) as r:return r.read().decode()\n'
            'if "gate" in sys.argv[2:]:post("authority-gate")\n'
            'print(post("effect"))\n'
            'if "public" not in sys.argv[2:]:print(Path('+repr(str(root/'workspace/private-authority.txt'))+').read_text())\n')
        for name in keys:
            c=token+'_'+name.upper()+'_READY';fixture.register(c)
            if not gateway.request(c,session_key=keys[name])['accepted']:raise RuntimeError('Native session initialization control failed')
            patch(name,'full')
            c=token+'_'+name.upper()+'_FULL_CONTROL'
            result=execute(c,name,'python3 '+str(script)+' '+c+(' public' if name=='restricted' else ''))
            if not result['accepted'] or fixture.receipts.get(c)!=1 or (name=='privileged' and canary not in json.dumps(fixture.tool_returns.get(c,[]))):
                raise RuntimeError('Both actual session exec positive controls must succeed before restricting one')
        patch('restricted','read-only');initial_pid=gateway.process.pid
        if mode=='restart':
            gateway.stop();gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready();wait_control(gateway,fixture,token+'_RESTART_READY')
            metadata['gateway_pid_changed']=initial_pid!=gateway.process.pid
            check('native-gateway-and-in-process-plugin-host-restarted',initial_pid!=gateway.process.pid)
            records.append(privacy_cases.wire(root,[dict(method='sessions.get',params=dict(key=session('restricted')))]))
        row.update(native_invoked=True,fixture_validated=True)
        allowed=token+'_ALLOWED';denied=token+'_DENIED'
        if mode=='cached-result':
            effect=token+'_CACHED_EFFECT';peer.register(effect)
            def cached(item,name):
                fixture.plan(item,'authority__eval_probe',dict(token=effect),canary)
                result=gateway.request(item,session_key=keys[name]);requests.append(result);return result
            for item in [token+'_CACHE_PRIME',token+'_CACHE_HIT']:
                if not cached(item,'privileged')['accepted']:raise RuntimeError('Actual MCP cached-result controls failed')
            if not any(e['kind']=='owned-cached-result-served' for e in peer.events):raise RuntimeError('External result cache was never actually reused')
            boundary=len(peer.events);result=cached(denied,'restricted')
            check('restricted-session-cannot-obtain-privileged-cached-result',not result['accepted'] and canary not in json.dumps(fixture.tool_returns.get(denied,[])))
            check('restricted-session-never-dispatched-to-external-result-cache',not any(e['kind'] in {'mcp-tool-start','owned-cached-result-served'} for e in peer.events[boundary:]))
            metadata['cache_scope']='Actual owned MCP result cache was populated and hit by privileged calls. No native internal cache hit or arbitrary plugin-code sandbox is claimed.'
        else:
            command='python3 '+str(script)+' '+allowed+(' gate' if mode=='concurrent' else '')
            if mode=='concurrent':
                fixture.allow_effect.clear()
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    pending=pool.submit(execute,allowed,'privileged',command)
                    if not fixture.entered.wait(timeout=12):fixture.allow_effect.set();raise RuntimeError('Actual privileged exec did not reach the independent concurrency gate')
                    begin=time.monotonic_ns();result=execute(denied,'restricted','python3 '+str(script)+' '+denied)
                    metadata['denied_attempt_while_privileged_exec_live']=not pending.done()
                    metadata['restricted_attempt_started_ns']=begin;fixture.allow_effect.set();positive=pending.result(timeout=40)
                check('restricted-attempt-overlaps-live-privileged-exec',metadata['denied_attempt_while_privileged_exec_live'])
            else:
                positive=execute(allowed,'privileged',command)
                result=execute(denied,'restricted','python3 '+str(script)+' '+denied)
            check('privileged-session-continues-to-run-one-real-command',positive['accepted'] and fixture.receipts.get(allowed)==1)
            check('restricted-session-does-not-inherit-exec-authority-or-private-result',not result['accepted'] and not fixture.receipts.get(denied) and canary not in json.dumps(fixture.tool_returns.get(denied,[])))
        neighbor=token+'_PUBLIC_NEIGHBOR';fixture.plan(neighbor,'read',dict(path=str(root/'workspace/public-neighbor.txt')),'OWNED_PUBLIC_NEIGHBOR')
        healthy=gateway.request(neighbor,session_key=keys['restricted']);requests.append(healthy)
        if any(e['kind']=='authority-gate-timeout' for e in fixture.events):raise RuntimeError('Independent authority gate timed out; overlap fixture invalid')
        check('restricted-session-still-performs-permitted-native-read',healthy['accepted'])
        check('private-result-absent-from-restricted-measured-model-input',canary not in json.dumps(fixture.native_inputs.get(denied,[])))
        check('measured-restricted-request-reaches-native-model',any(e.get('token')==denied and e['kind']=='native-operation-provider-request' for e in fixture.events))
        metadata.update(mode=mode,permission_modes=dict(privileged='full',restricted='read-only'),gateway_pid=gateway.process.pid,
            plugin_host_boots=[json.loads(line) for line in (root/'workspace/plugin-host-boots.jsonl').read_text().splitlines()],
            scope='Two native sessions in one shared Gateway. OS exec children are fresh processes. Restart replaces the actual Gateway and its in-process plugin host, not an invented separate plugin worker. This is session tool authority, not protection against trusted plugin JavaScript or a hostile OS user.')
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,
            native_policy_records=records,native_tool_returns=fixture.tool_returns,resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2300],metadata=metadata,native_policy_records=records)
    finally:
        fixture.allow_effect.set()
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-3000:]
        row.update(requests=requests,independent_events=fixture.events,independent_receipts=fixture.receipts,independent_cache_events=peer.events if peer else [])
        if peer:peer.close()
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
