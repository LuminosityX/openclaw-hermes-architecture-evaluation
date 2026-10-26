"""Run one native real-model task. This file contains no hidden acceptance data."""
import hashlib
import http.client
import json
from pathlib import Path
import resource
import sys
import time

import pilot
from provider_bridge import bridge
from task_cases import TaskFixture, configure, selfcheck


def main():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    for name in ['tmp','home','cache','run']: (pilot.BASE/name).mkdir(exist_ok=True)
    spec=json.loads(Path('/task/input.json').read_text())
    task=spec['task']
    file_limit=(64 if task.get('reuse') else 16)*1024**2
    resource.setrlimit(resource.RLIMIT_FSIZE,(file_limit,file_limit))
    fixture_class=TaskFixture;configure_task=configure;check_fixture=selfcheck
    if task.get('injection'):
        from injection_cases import InjectionFixture,configure as injection_configure,selfcheck as injection_selfcheck
        fixture_class=InjectionFixture;configure_task=injection_configure;check_fixture=injection_selfcheck
    root=pilot.BASE/'task-unit'
    report=dict(kind='native-task-unit',product='openclaw',studies=[],task_id=task['task_id'],
                full_campaign_coverage=spec.get('full_campaign_coverage') is True,artifacts={},independent_events=[],per_file_limit_bytes=file_limit)
    fixture=None;gateway=None;server=None
    try:
        report['storage_guard_check']=pilot.storage_guard_check()
        report['fixture_selfcheck']=check_fixture(task)
        fixture=fixture_class(root,task)
        server=bridge()
        if task.get('billing'):
            from billing_cases import execute
            execute(root,task,report)
        elif task.get('reuse'):
            from reuse_cases import execute
            execute(root,task,spec['thinking']=='enabled',report,fixture)
        elif task.get('conversation'):
            from conversation_cases import execute
            gateway=execute(root,task,spec['thinking']=='enabled',report,server,fixture)
        else:
            gateway=pilot.Gateway(root,configurer=lambda root:configure_task(root,task,thinking=spec['thinking']=='enabled'))
            gateway.ready()
            prompt=task['task_id']+'\n'+task['prompt']+'\nAvailable files: '+', '.join(sorted(task['files']))
            connection=http.client.HTTPConnection('127.0.0.1',18789,timeout=task['resource_limits']['timeout_seconds'])
            started=time.monotonic_ns()
            try:
                connection.request('POST','/v1/chat/completions',json.dumps(dict(model='openclaw',stream=False,messages=[dict(role='user',content=prompt)])),
                    {'Content-Type':'application/json','Authorization':'Bearer '+pilot.TOKEN,'x-openclaw-session-key':'agent:main:eval:'+task['task_id'].lower()})
                response=connection.getresponse()
                raw=response.read(1024**2+1)
                if len(raw)>1024**2: raise ValueError('Native response exceeded task protocol byte limit')
                report.update(native_http_status=response.status,response_sha256=hashlib.sha256(raw).hexdigest(),response_bytes=len(raw))
                if task.get('injection'):report['synthetic_private_canary_in_native_response']=task['injection']['private_canary'].encode() in raw
            except (OSError,http.client.HTTPException) as error:
                report['task_transport_error']=type(error).__name__
            finally: connection.close()
            report.update(completion_ms=(time.monotonic_ns()-started)/1e6,
                          resources=gateway.sampler.summary(),config_sha256=hashlib.sha256((root/'config.json').read_bytes()).hexdigest())
    except Exception as error:
        report['harness_error']=type(error).__name__+': '+str(error)[:2000]
    finally:
        if gateway: gateway.stop()
        if not task.get('reuse') and not task.get('billing'):
            report['input_integrity']={name:(root/'workspace'/name).is_file() and not (root/'workspace'/name).is_symlink() and (root/'workspace'/name).read_text()==content
                for name,content in task['files'].items() if name!=task['artifact']}
            path=root/'workspace'/task['artifact']
            if path.is_file() and not path.is_symlink():
                if path.stat().st_size<=128*1024: report['artifacts'][task['artifact']]=path.read_text()
                else: report['artifact_size_limit_exceeded']=True
        if fixture:
            report['independent_events']=fixture.task_events
            fixture.close()
        if server:
            server.shutdown();server.server_close()
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if report.get('harness_error'): sys.exit(1)


if __name__=='__main__': main()
