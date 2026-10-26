"""Separate actual tool delegation, provider decoration and native harness ownership."""
import hashlib
import json
from pathlib import Path
import shutil
import time

from effect_recovery_cases import wait_control
from operation_fixture import OperationFixture
import pilot
import privacy_cases
import service_path_cases as service

HARNESS='eval-external-harness'
SCENARIOS={f'EXT-02-S{i:02}':mode for i,mode in enumerate(['tool','provider','harness','resume'],1)}


class HarnessFixture(OperationFixture):
    def __init__(self):self.harness_events=[];super().__init__()
    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def do_POST(self):
                if self.path!='/harness-event':return super().do_POST()
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=16384:return self.send(dict(error='bounded-executor-event'),413)
                body=json.loads(self.rfile.read(size));event=dict(body,monotonic_ns=time.monotonic_ns())
                owner.harness_events.append(event);return self.send(dict(observed=True))
        return Handler


def configure(root,mode):
    config=service.configure(root)
    if mode in {'tool','provider'}:
        config['mcp']=dict(servers=dict(external=dict(transport='stdio',command='/usr/bin/python3',args=['/driver/external_harness_worker.py'],requestTimeoutMs=5000,connectionTimeoutMs=5000)))
        config['tools']['allow'].append('external__eval_probe')
    if mode=='provider':
        directory=root/'reference-provider';directory.mkdir()
        pilot.save(directory/'package.json',dict(name='eval-reference-provider',version='1.0.0',type='module',openclaw=dict(extensions=['./index.mjs'])))
        pilot.save(directory/'openclaw.plugin.json',dict(id='eval-reference-provider',providers=['fixture'],activation=dict(onStartup=True),configSchema=dict(type='object',properties={},additionalProperties=False)))
        log=root/'workspace/provider-callbacks.jsonl'
        (directory/'index.mjs').write_text("import fs from 'node:fs';\nexport default {id:'eval-reference-provider',register(api){api.registerProvider({id:'fixture',label:'Owned fixture provider decoration',auth:[],wrapStreamFn(ctx){if(!ctx.streamFn)throw new Error('HOST_STREAM_REQUIRED');return Object.assign((...args)=>{fs.appendFileSync("+json.dumps(str(log))+",JSON.stringify({pid:process.pid,model:ctx.model?.id,at:Date.now()})+'\\n');return ctx.streamFn(...args);},{preservesGenericCompatibility:true});}});}};\n")
        config['plugins']['allow'].append('eval-reference-provider');config['plugins']['load']['paths'].append(str(directory));config['plugins']['entries']['eval-reference-provider']=dict(enabled=True)
    if mode in {'harness','resume'}:
        directory=root/'external-harness';directory.mkdir()
        pilot.save(directory/'package.json',dict(name=HARNESS,version='1.0.0',type='module',openclaw=dict(extensions=['./index.mjs'])))
        pilot.save(directory/'openclaw.plugin.json',dict(id=HARNESS,categories=['agent-runtimes'],activation=dict(onStartup=True,onAgentHarnesses=[HARNESS]),configSchema=dict(type='object',properties=dict(state_directory=dict(type='string')),required=['state_directory'],additionalProperties=False)))
        shutil.copyfile(Path(__file__).with_name('harness_reference.mjs'),directory/'index.mjs')
        config['plugins']['allow'].append(HARNESS);config['plugins']['load']['paths'].append(str(directory));config['plugins']['entries'][HARNESS]=dict(enabled=True,config=dict(state_directory=str(root/'workspace/external-runtime-state')))
    pilot.save(root/'config.json',config);return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];token='PILOT_HARNESS_'+scenario.replace('-','_')+'_U'+str(unit)
    task=dict(task_id='owned-arithmetic-'+scenario+'-'+str(unit),operation='add',left=137+unit,right=286-unit)
    fixture=HarnessFixture();gateway=None;assertions=[];metadata={};requests=[];exports=[]
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['actual-public-harness-or-provider-callback','independent-external-process-and-checkpoint-events','native-public-transcript-and-session-records']))
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:configure(p,mode));gateway.ready();wait_control(gateway,fixture,token+'_CONTROL')
        if mode in {'tool','provider'}:
            fixture.plan(token,'external__eval_probe',dict(token=token,left=task['left'],right=task['right']),'ANSWER:423')
            result=gateway.request(token);requests.append(result)
            effects=[e for e in fixture.harness_events if e['kind']=='external-tool-result' and e.get('token')==token]
            if not effects:raise RuntimeError('Actual native external MCP execution was not established')
            row.update(native_invoked=True,fixture_validated=True)
            check('actual-external-tool-computes-public-inputs',result['accepted'] and fixture.receipts.get(token)==1 and effects[0]['value']==423)
            check('tool-process-is-distinct-from-native-gateway',all(e['pid']!=gateway.process.pid for e in effects))
            check('native-provider-loop-still-owns-tool-dispatch',bool(fixture.native_inputs.get(token)) and bool(fixture.tool_returns.get(token)))
            if mode=='provider':
                path=root/'workspace/provider-callbacks.jsonl'
                callbacks=[json.loads(line) for line in path.read_text().splitlines()] if path.is_file() else []
                if not callbacks:raise RuntimeError('Registered reference provider decorator never actually ran')
                metadata['actual_provider_callbacks']=callbacks
                check('provider-decoration-preserves-native-loop-and-external-result',result['accepted'] and fixture.receipts.get(token)==1)
        else:
            key=token.lower();session='agent:main:pilot:'+key;c=token+'_SESSION_CONTROL';fixture.register(c)
            if not gateway.request(c,session_key=key)['accepted']:raise RuntimeError('Native target-session initialization failed')
            patch=privacy_cases.wire(root,[dict(method='sessions.patch',params=dict(key=session,permissionMode='full',agentRuntime=HARNESS)),dict(method='sessions.get',params=dict(key=session))])
            metadata['native_runtime_selection']=patch
            if not patch['responses'][0]['result'].get('ok'):raise RuntimeError('Public native harness selection failed: '+json.dumps(patch)[:1800])
            if mode=='resume':task['fail_once']=True
            begin=len(fixture.events)
            result=privacy_cases.request(gateway,token,session,'HARNESS_TASK '+json.dumps(task));requests.append(result)
            attempts=[e for e in fixture.harness_events if e['kind']=='native-harness-attempt']
            if not attempts:raise RuntimeError('Selected public harness runAttempt was never actually invoked: '+json.dumps(result)[:1200])
            row.update(native_invoked=True,fixture_validated=True)
            if mode=='resume':
                failed=[e for e in fixture.harness_events if e['kind']=='external-checkpoint-then-exit' and e.get('exit_code')==73]
                if not failed:raise RuntimeError('Actual external executor failure after its own checkpoint was not injected')
                pid=gateway.process.pid;gateway.stop();gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready();wait_control(gateway,fixture,token+'_RESTART_READY')
                continued=token+'_CONTINUE';result=privacy_cases.request(gateway,continued,session,'HARNESS_TASK '+json.dumps(task));requests.append(result)
                check('actual-native-gateway-restarted-with-same-session-selection',gateway.process.pid!=pid)
                metadata.update(operator_restart=True,first_request_accepted=requests[0]['accepted'],continued_token=continued)
            actual=[e for e in fixture.harness_events if e['kind']=='external-attempt-result' and e.get('task_id')==task['task_id']]
            check('external-harness-completes-real-public-computation',result['accepted'] and bool(actual) and all(e['value']==423 for e in actual))
            check('external-executor-process-is-distinct',bool(actual) and all(e['pid']!=gateway.process.pid for e in actual))
            measured_provider=[e for e in fixture.events[begin:] if 'provider' in e['kind'] and e.get('token') in {token,token+'_CONTINUE'}]
            check('full-harness-turn-does-not-use-the-core-provider-tool-loop',not measured_provider)
            if mode=='resume':check('checkpointed-external-computation-is-reused',bool(actual) and actual[-1]['resumed'] and all(e['calculation_count']==1 for e in actual))
            exported=privacy_cases.history(root,session);exports.append(exported)
            check('real-harness-answer-is-in-native-public-transcript','ANSWER:423' in json.dumps(exported))
            metadata.update(actual_attempts=attempts,checkpoint_files=[dict(name=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (root/'workspace/external-runtime-state').rglob('*.json')])
        metadata.update(mode=mode,public_task=task,scope='Bounded deterministic integration task, not real model quality. The reference external harness is literally tool-free and host-only, uses the public user recorder and transcript SDK, and owns only its separate arithmetic checkpoint. Its deliberate exit after a pure-computation checkpoint is not an external business-effect recovery guarantee.',core_edits=0,private_imports=0)
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,native_exports=exports,native_tool_returns=fixture.tool_returns,resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2400],metadata=metadata)
    finally:
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-5000:]
        row.update(requests=requests,independent_harness_events=fixture.harness_events,independent_events=fixture.events,independent_receipts=fixture.receipts)
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
