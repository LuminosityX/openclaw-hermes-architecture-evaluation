"""Same native conversation through controlled history, LLM compaction and restart."""
import hashlib
import http.client
import json
import os
import subprocess
import time

import pilot
import recovery_cases
import task_cases


def configure(root,task,thinking=False):
    config=task_cases.configure(root,task,thinking)
    config['models']['providers']['deepseek']['models'][0]['contextWindow']=task['conversation']['context_window']
    config['agents']['defaults']['compaction']=dict(enabled=False,keepRecentTokens=512,recentTurnsPreserve=1,
        timeoutSeconds=120,memoryFlush=dict(enabled=False),qualityGuard=dict(enabled=False))
    pilot.save(root/'config.json',config);return config


def turn(gateway,session,message,timeout):
    connection=http.client.HTTPConnection('127.0.0.1',18789,timeout=timeout);start=time.monotonic_ns()
    try:
        connection.request('POST','/v1/chat/completions',json.dumps(dict(model='openclaw',stream=False,messages=[dict(role='user',content=message)])),
            {'Content-Type':'application/json','Authorization':'Bearer '+pilot.TOKEN,'x-openclaw-session-key':session})
        response=connection.getresponse();raw=response.read(1024**2+1)
        if len(raw)>1024**2:raise RuntimeError('Native conversation response exceeds bound')
        return dict(status=response.status,latency_ms=(time.monotonic_ns()-start)/1e6,response_sha256=hashlib.sha256(raw).hexdigest(),response_bytes=len(raw),
            error_excerpt=raw.decode(errors='replace')[:1000] if response.status!=200 else None)
    except (OSError,http.client.HTTPException) as error:return dict(status=None,latency_ms=(time.monotonic_ns()-start)/1e6,error_type=type(error).__name__)
    finally:connection.close()


def compact(root,session):
    env=dict(os.environ,OPENCLAW_STATE_DIR=str(root/'state'),OPENCLAW_CONFIG_PATH=str(root/'config.json'),
        OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_DISABLE_BUNDLED_PLUGINS='1')
    start=time.monotonic_ns()
    result=subprocess.run([pilot.NODE,pilot.CLI,'sessions','compact',session,'--json','--timeout','150000'],
        env=env,capture_output=True,text=True,timeout=170)
    try:payload=json.loads(result.stdout)
    except ValueError:payload=None
    return dict(returncode=result.returncode,payload=payload,stdout=result.stdout[-4000:],stderr=result.stderr[-2000:],latency_ms=(time.monotonic_ns()-start)/1e6)


def execute(root,task,thinking,report,bridge_server,fixture):
    gateway=None;session='agent:main:eval:'+task['task_id'].lower();steps=[]
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:configure(p,task,thinking));gateway.ready()
        for index,prompt in enumerate(task['conversation']['primers']):
            result=turn(gateway,session,prompt,60);steps.append(dict(stage='primer',index=index,**result))
            if result['status']!=200:
                report.update(task_transport_error='PrimingFailed',native_http_status=result['status'],completion_ms=0,
                    conversation_condition_exercised=False);return gateway
        if task['conversation']['force_native_compaction']:
            result=compact(root,session);report['native_compaction']=result
            report['native_compaction_exercised']=result['returncode']==0 and isinstance(result['payload'],dict) and result['payload'].get('compacted') is True
        if task['conversation']['restart_before_final']:
            before=gateway.process.pid;gateway.stop();gateway=pilot.Gateway(root,configurer=lambda p:json.loads((p/'config.json').read_text()));gateway.ready()
            report.update(native_restart_exercised=gateway.process.pid!=before,pre_restart_process_pid=before,post_restart_process_pid=gateway.process.pid)
        prompt='FINAL_STAGE '+task['task_id']+'\n'+task['prompt']+'\nAvailable files: '+', '.join(sorted(task['files']))
        deadline=time.monotonic()+30
        while True:
            prior_logs=set(gateway.log_tail);before_requests=bridge_server.forwarded_requests;before_tools=len(fixture.task_events)
            result=turn(gateway,session,prompt,task['resource_limits']['timeout_seconds']);steps.append(dict(stage='final',**result))
            fresh_logs=''.join(line for line in gateway.log_tail if line not in prior_logs)
            provider_seen=bridge_server.forwarded_requests!=before_requests;tool_effects=len(fixture.task_events)-before_tools
            if not (task['conversation']['restart_before_final'] and recovery_cases.pending_admission(result,fresh_logs,provider_seen,tool_effects)) or time.monotonic()>=deadline:break
            # Admission-only rejections are known not to enter the model path.
            # Never replay a timeout, disconnected request or admitted work.
            time.sleep(.5)
        report.update(native_http_status=result['status'],completion_ms=result['latency_ms'],conversation_condition_exercised=True,
            resources=gateway.sampler.summary(),config_sha256=hashlib.sha256((root/'config.json').read_bytes()).hexdigest())
        if result.get('error_type'):report['task_transport_error']=result['error_type']
        return gateway
    except Exception:
        if gateway:gateway.stop()
        raise
    finally:
        report['conversation_steps']=steps
        report['conversation_profile']=dict(primer_count=len(task['conversation']['primers']),
            primer_user_bytes=sum(len(p.encode()) for p in task['conversation']['primers']),source_bytes=task['conversation']['source_bytes'],
            context_window=task['conversation']['context_window'],automatic_compaction=False,
            scope='Explicit native LLM summarization only in S03; clean native process restart with the same owned state only in S05. No transcript truncation, handcrafted summary or patched runtime.')
        if gateway:report['native_gateway_tail']=''.join(gateway.log_tail)[-3000:]
