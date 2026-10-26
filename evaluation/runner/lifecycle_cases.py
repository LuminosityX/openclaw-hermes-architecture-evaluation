"""Native deployment rebind, public extension lifecycle and bounded soak tests."""
import concurrent.futures
from http.server import ThreadingHTTPServer
import json
import io
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
import time

import mechanism_cases as mechanism
import pilot
import service_path_cases as service

FAMILIES={
    'REL-09':['endpoint-change','credential-rotation','old-endpoint-down','old-credential-revoked'],
    'EXT-01':['disable','inflight-reload','uninstall-restart','failed-replacement'],
    'PERF-08':['steady','new-sessions','connection-errors','drain'],
}
SCENARIOS={f'{family}-S{i:02}':name for family,names in FAMILIES.items() for i,name in enumerate(names,1)}


class RebindFixture(service.InstrumentedFixture):
    def __init__(self):
        self.grants={18082:'synthetic-generation-a',18084:'synthetic-generation-b'}
        self.first=None;self.second=None
        super().__init__()
        self.first=ThreadingHTTPServer(('127.0.0.1',18082),self.handler())
        self.second=ThreadingHTTPServer(('127.0.0.1',18084),self.handler())
        for server in [self.first,self.second]:
            server.daemon_threads=True
            threading.Thread(target=server.serve_forever,daemon=True).start()

    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def do_POST(self):
                if self.path.endswith('/chat/completions'):
                    port=self.server.server_address[1]
                    valid=self.headers.get('Authorization')=='Bearer '+owner.grants[port]
                    owner.event('credential-check',endpoint_port=port,authorized=valid,
                        credential_generation='b' if self.headers.get('Authorization')=='Bearer synthetic-generation-b' else 'a-or-invalid')
                    if not valid:
                        self.rfile.read(int(self.headers.get('Content-Length','0')))
                        return self.send(dict(error=dict(message='synthetic credential revoked',type='authentication_error')),401)
                return super().do_POST()
        return Handler

    def close_old(self):
        self.first.shutdown();self.first.server_close();self.first=None

    def close(self):
        for server in [self.server,self.first,self.second]:
            if server:server.shutdown();server.server_close()


class DisconnectFixture(service.InstrumentedFixture):
    def __init__(self):
        self.drop_tokens=set();self.dropped=set()
        super().__init__()

    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def do_POST(self):
                if self.path.endswith('/chat/completions'):
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=4*1024**2:return self.send(dict(error='fixture-bound'),413)
                    raw=self.rfile.read(size);body=json.loads(raw)
                    users=[str(m.get('content','')) for m in body.get('messages',[]) if m.get('role')=='user']
                    matches=[re.search(r'PILOT_[A-Z0-9_]+',text) for text in users]
                    marked=[m.group() for m in matches if m];token=marked[-1] if marked else None
                    if token in owner.drop_tokens and token not in owner.dropped:
                        owner.dropped.add(token);owner.event('provider-connection-dropped',token=token)
                        self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
                    original=self.rfile;self.rfile=io.BytesIO(raw)
                    try:return super().do_POST()
                    finally:self.rfile=original
                return super().do_POST()
        return Handler


def configure_rebind(root):
    config=service.configure(root)
    config['models']['providers']['fixture'].update(apiKey='synthetic-generation-a',baseUrl='http://127.0.0.1:18082/v1')
    pilot.save(root/'config.json',config)
    return config


def plugin_command(root,*arguments):
    env=dict(os.environ,OPENCLAW_STATE_DIR=str(root/'state'),OPENCLAW_CONFIG_PATH=str(root/'config.json'),
        OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_DISABLE_BUNDLED_PLUGINS='1')
    start=time.monotonic_ns()
    result=subprocess.run([pilot.NODE,pilot.CLI,'plugins',*arguments],env=env,capture_output=True,text=True,timeout=100)
    return dict(arguments=list(arguments),returncode=result.returncode,stdout=result.stdout[-6000:],stderr=result.stderr[-3000:],
        latency_ms=(time.monotonic_ns()-start)/1e6)


def run_scenario(root,scenario,unit=1):
    family=scenario.rsplit('-S',1)[0];mode=SCENARIOS[scenario]
    token='PILOT_LIFECYCLE_'+scenario.replace('-','_')+'_U'+str(unit)
    fixture=RebindFixture() if family=='REL-09' else DisconnectFixture() if family=='PERF-08' and mode=='connection-errors' else service.InstrumentedFixture()
    gateway=None;assertions=[];requests=[];metadata={};timeline=[]
    row=dict(scenario_id=scenario,unit=unit,fixture_validated=False,native_invoked=False)
    def check(name,condition,evidence=('native-product-records','independent-events')):
        assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=list(evidence)))
    def register(label,**options):
        item=token+'_'+label;fixture.register(item,**options);return item
    def record(label):
        timeline.append(dict(label=label,monotonic_ns=time.monotonic_ns(),
            process=mechanism.process_snapshot(gateway.process.pid),disk=service.owned_inventory(root,gateway.process.pid)))
    def request(item,session=None):
        result=gateway.request(item,session_key=session)
        requests.append({k:v for k,v in result.items() if k!='response_excerpt'})
        return result
    try:
        configurer=configure_rebind if family=='REL-09' else (lambda p:mechanism.configure(p,'EXT-09-S01')) if family=='EXT-01' else service.configure
        gateway=pilot.Gateway(root,configurer=configurer);gateway.ready()
        control=register('CONTROL');positive=request(control,session=token.lower()+'_continuation')
        if not positive['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Native receipt positive control failed')
        row.update(fixture_validated=True,native_invoked=True)
        record('positive-control-complete')
        if family=='REL-09':
            gateway.stop()
            config=json.loads((root/'config.json').read_text())
            changed_endpoint=mode in {'endpoint-change','old-endpoint-down'}
            target=18084 if changed_endpoint else 18082
            config['models']['providers']['fixture'].update(baseUrl=f'http://127.0.0.1:{target}/v1',apiKey='synthetic-generation-b')
            fixture.grants[target]='synthetic-generation-b'
            if mode=='old-endpoint-down':fixture.close_old()
            if mode=='old-credential-revoked':
                connection=service.http.client.HTTPConnection('127.0.0.1',target,timeout=3)
                connection.request('POST','/v1/chat/completions','{}',{'Authorization':'Bearer synthetic-generation-a','Content-Type':'application/json'})
                response=connection.getresponse();response.read();metadata['revoked_credential_positive_denial_status']=response.status;connection.close()
                if response.status!=401:raise RuntimeError('Revocation fixture did not reject the old synthetic credential')
            pilot.save(root/'config.json',config)
            begin=len(fixture.events)
            gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready()
            continued=register('CONTINUED');result=request(continued,session=token.lower()+'_continuation')
            events=fixture.events[begin:];grants=[e for e in events if e['kind']=='credential-check']
            check('resumed-task-completes-on-new-deployment-binding',result['accepted'] and fixture.receipts.get(continued)==1)
            check('new-binding-only-used',bool(grants) and all(e['authorized'] and e['endpoint_port']==target and e['credential_generation']=='b' for e in grants))
            native=pilot.native_evidence(root,[control,continued])
            check('pre-and-post-rebind-transcript-evidence-preserved',all(v['token_seen'] and v['receipt_seen'] for v in native['tokens'].values()))
            metadata.update(native_records=native,source_endpoint_port=18082,target_endpoint_port=target,
                migration_scope='Same pinned runtime and existing state/workspace, changed deployment provider binding followed by native restart. No external OAuth identity migration is claimed.')
        elif family=='EXT-01':
            independent=register('OTHER',tool='eval_other');other=request(independent)
            if not other['accepted'] or fixture.receipts.get(independent)!=1:raise RuntimeError('Unaffected plugin positive control failed')
            command=None
            if mode=='disable':
                command=plugin_command(root,'disable','composition-a')
                if command['returncode']:raise RuntimeError('Native disable command failed: '+json.dumps(command))
                time.sleep(.5)
                denied=register('AFTER_DISABLE');result=request(denied)
                check('new-call-after-disable-has-no-effect',not result['accepted'] and not fixture.receipts.get(denied))
            elif mode=='inflight-reload':
                slow=register('INFLIGHT',delay=1.5)
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pending=pool.submit(request,slow)
                    if not mechanism.wait_events(fixture,'effect-start',[slow]):raise RuntimeError('In-flight replacement boundary was not reached')
                    plugin=root/'composition-a/index.js'
                    plugin.write_text(plugin.read_text().replace('const owner="composition-a";','const owner="composition-a-generation-2";'))
                    command=plugin_command(root,'reload','composition-a','--wait','--json')
                    prior=pending.result(timeout=40)
                if command['returncode']:raise RuntimeError('Native reload command failed: '+json.dumps(command))
                next_item=register('NEW_GENERATION');next_result=request(next_item)
                owners=[e.get('owner') for e in fixture.events if e['kind']=='effect-commit' and e.get('token')==next_item]
                check('retained-inflight-call-completes-exactly-once',prior['accepted'] and fixture.receipts.get(slow)==1)
                check('replacement-serves-new-calls',next_result['accepted'] and owners==['composition-a-generation-2'])
            elif mode=='uninstall-restart':
                # A linked source must have a native install record so uninstall
                # exercises the documented lifecycle instead of deleting files.
                installed=plugin_command(root,'install',str(root/'composition-a'),'--link','--force','--accept-capabilities')
                if installed['returncode']:raise RuntimeError('Native linked install failed: '+json.dumps(installed))
                metadata['linked_install']=installed
                command=plugin_command(root,'uninstall','composition-a','--force')
                if command['returncode']:raise RuntimeError('Native uninstall command failed: '+json.dumps(command))
                gateway.stop();gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready()
                denied=register('AFTER_UNINSTALL');result=request(denied)
                check('restart-does-not-resurrect-uninstalled-plugin',not result['accepted'] and not fixture.receipts.get(denied))
                metadata['source_files_preserved']=bool((root/'composition-a/index.js').exists())
                metadata['uninstall_scope']='Native linked-source uninstall; user-owned linked source is intentionally preserved.'
            else:
                plugin=root/'composition-a/index.js';plugin.write_text("throw new Error('EVAL_REPLACEMENT_STARTUP_FAILURE');\n")
                command=plugin_command(root,'reload','composition-a','--json')
                check('failed-replacement-reported-visibly',command['returncode']!=0 and bool(command['stdout'] or command['stderr']))
                next_item=register('OLD_GENERATION');result=request(next_item)
                check('previous-usable-generation-preserved',result['accepted'] and fixture.receipts.get(next_item)==1)
            healthy=register('HEALTHY_AFTER',tool='eval_other');health=request(healthy)
            check('unrelated-plugin-remains-usable',health['accepted'] and fixture.receipts.get(healthy)==1)
            metadata.update(lifecycle_command=command,public_api_only=True,core_files_modified=0,
                source_policy='Only owned synthetic plugin source is changed for replacement. Runtime core stays read-only.')
        else:
            # Finite hosted smoke-soak, with complete duration and all offered
            # work accounted for. No claim about multi-hour stability is made.
            duration=60;start=time.monotonic();deadline=start+duration;index=0;stop=None
            while time.monotonic()<deadline:
                item=register('T'+str(index))
                if mode=='connection-errors':
                    fixture.drop_tokens.add(item)
                    metadata['disconnect_injection']='Provider closes the first actual completion connection for each new task before any response bytes; native retry and subsequent complete receipt are independently observed.'
                result=request(item,session=token.lower()+'_steady' if mode in {'steady','drain'} else None)
                check('offered-task-'+str(index)+'-completed',result['accepted'] and fixture.receipts.get(item)==1)
                record('work-'+str(index));index+=1
                time.sleep(min(1,max(0,deadline-time.monotonic())))
            stop=time.monotonic()
            metadata.update(predeclared_duration_seconds=duration,actual_work_seconds=stop-start,offered_requests=index,
                workload='Closed finite loop with 1 s inter-request dwell; the actual offered/accepted count and wall duration are retained.',
                leak_criterion='Flag PSS growth above 1 MiB/s or live-fd growth above 0.25/s across the measured window for follow-up. These are diagnostic screening thresholds, not proof of a leak or a product correctness promise. Native task outcomes and complete duration are scored separately; this is not multi-hour stability evidence.',
                censored=stop-start<duration)
            check('predeclared-work-duration-completed',stop-start>=duration)
            if mode=='connection-errors':check('actual-provider-disconnects-injected',len(fixture.dropped)==index and index>0)
            if mode=='drain':
                time.sleep(3);record('three-second-idle-drain')
                metadata['drain_idle_seconds']=3
            if len(timeline)>1:
                first,last=timeline[0],timeline[-1];elapsed=(last['monotonic_ns']-first['monotonic_ns'])/1e9
                metadata['observed_slopes_per_second']={key:(last['process'][key]-first['process'][key])/elapsed for key in ['pss_bytes','open_fds','threads','processes']}
                metadata['observed_slopes_per_second']['allocated_disk_bytes']=(last['disk']['allocated_bytes']-first['disk']['allocated_bytes'])/elapsed
                slopes=metadata['observed_slopes_per_second']
                metadata['leak_screening_flags']=dict(pss_growth=slopes['pss_bytes']>1024**2,fd_growth=slopes['open_fds']>.25)
        record('before-stop')
        check('no-duplicated-independent-effects',all(value<=1 for value in fixture.receipts.values()))
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            requests=requests,metadata=metadata,timeline=timeline,independent_events=fixture.events,
            independent_receipts=fixture.receipts,resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:3500],metadata=metadata)
    finally:
        if gateway:gateway.stop()
        fixture.close();shutil.rmtree(root,ignore_errors=True)
        row['owned_state_retained']=root.exists()
    return row
