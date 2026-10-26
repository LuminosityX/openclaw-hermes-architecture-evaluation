"""Native OTLP log publication, independently compared with local event IDs."""
from collections import Counter
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import sqlite3
import threading
import time
import zlib

from effect_recovery_cases import wait_control
import pilot
import service_path_cases as service

SCENARIOS={f'OBS-02-S{i:02}':name for i,name in enumerate(['brief','long','restart','overflow'],1)}
EVENT=re.compile(r'EVAL_OBS_EVENT_PILOT_[A-Z0-9_]+_N\d{5}')
ADDON_TEMPLATE=Path('/official-addon.json')
ADDON=Path(json.loads(ADDON_TEMPLATE.read_text())['package_root']) if ADDON_TEMPLATE.is_file() else Path('/runtime/node_modules/@openclaw/diagnostics-otel')


def fields(data):
    """Bounded independent protobuf framing, without importing runtime internals."""
    if len(data)>4*1024**2:raise ValueError('Owned protobuf bound')
    offset=0;items=[]
    def integer():
        nonlocal offset
        value=0
        for shift in range(0,70,7):
            if offset>=len(data):raise ValueError('Truncated protobuf varint')
            byte=data[offset];offset+=1;value|=(byte&127)<<shift
            if byte<128:return value
        raise ValueError('Oversized protobuf varint')
    while offset<len(data):
        tag=integer();number=tag>>3;wire=tag&7
        if not number:raise ValueError('Invalid protobuf field')
        if wire==0:value=integer()
        else:
            size=integer() if wire==2 else 8 if wire==1 else 4 if wire==5 else None
            if size is None or offset+size>len(data):raise ValueError('Invalid protobuf wire length')
            value=data[offset:offset+size];offset+=size
        items.append((number,wire,value))
    return items


def log_event_ids(data):
    result=[]
    for n,w,resource in fields(data):
        if (n,w)!=(1,2):continue
        for n,w,scope in fields(resource):
            if (n,w)!=(2,2):continue
            for n,w,record in fields(scope):
                if (n,w)!=(2,2):continue
                for n,w,body in fields(record):
                    if (n,w)!=(5,2):continue
                    for n,w,value in fields(body):
                        if (n,w)==(1,2):result.extend(EVENT.findall(value.decode('utf-8',errors='replace')))
    return result


class Collector:
    def __init__(self):
        self.fail=False;self.attempts=[];self.deliveries=Counter();self.lock=threading.Lock()
        self.server=ThreadingHTTPServer(('127.0.0.1',18088),self.handler());self.server.daemon_threads=True
        threading.Thread(target=self.server.serve_forever,daemon=True).start()

    def handler(self):
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4*1024**2:self.send_error(413);return
                raw=self.rfile.read(size)
                if self.headers.get('Content-Encoding')=='gzip':
                    raw=zlib.decompressobj(16+zlib.MAX_WBITS).decompress(raw,4*1024**2+1)
                try:ids=log_event_ids(raw)
                except ValueError as error:
                    with owner.lock:owner.attempts.append(dict(parser_error=str(error),bytes=len(raw)))
                    self.send_error(400);return
                with owner.lock:
                    status=503 if owner.fail else 200
                    owner.attempts.append(dict(monotonic_ns=time.monotonic_ns(),status=status,ids=ids,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
                    if status==200:owner.deliveries.update(ids)
                self.send_response(status);self.send_header('Content-Type','application/x-protobuf');self.send_header('Content-Length','0');self.end_headers()
        return Handler

    def close(self):self.server.shutdown();self.server.server_close()


def configure(root,count,target):
    package=json.loads((ADDON/'package.json').read_text())
    if package['version']!='2026.10.7':raise RuntimeError('Official diagnostics addon version differs from campaign')
    config=service.configure(root)
    template=json.loads(ADDON_TEMPLATE.read_text())
    snapshot=Path('/official-addon-state.sqlite')
    if hashlib.sha256(snapshot.read_bytes()).hexdigest()!=template['native_state_snapshot_sha256']:raise RuntimeError('Native addon install-state snapshot digest mismatch')
    directory=root/'state/state';directory.mkdir(mode=0o700)
    source=sqlite3.connect('file:'+str(snapshot)+'?mode=ro',uri=True);target=sqlite3.connect(str(directory/'openclaw.sqlite'));source.backup(target);target.close();source.close()
    (directory/'openclaw.sqlite').chmod(0o600)
    config['plugins']['allow'].append('diagnostics-otel');config['plugins']['load']['paths'].append(str(ADDON));config['plugins']['entries']['diagnostics-otel']=template['entry_configuration']
    config['diagnostics']=dict(enabled=True,otel=dict(enabled=True,endpoint='http://127.0.0.1:18088',protocol='http/protobuf',
        serviceName='owned-openclaw-evaluation',traces=False,metrics=False,logs=True,logsExporter='otlp',flushIntervalMs=1000,captureContent=True))
    plugin=root/'composition-a/index.js';source=plugin.read_text().replace('  await announce(\'entered\');',
        "  await announce('entered');\n  for(let index=0;index<(args.token==="+json.dumps(target)+"?"+str(count)+":8);index++)api.logger.info('EVAL_OBS_EVENT_'+args.token+'_N'+String(index).padStart(5,'0')); ")
    plugin.write_text(source);pilot.save(root/'config.json',config);return config


def wait_delivered(collector,prefix,seconds=12):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if any(k.startswith(prefix) for k in collector.deliveries):return True
        time.sleep(.1)
    return False


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];count=4096 if mode=='overflow' else 8
    fixture=service.InstrumentedFixture();collector=Collector();gateway=None;assertions=[];metadata={};requests=[]
    token='PILOT_COLLECTOR_'+scenario.replace('-','_')+'_U'+str(unit);prefix='EVAL_OBS_EVENT_'+token+'_N'
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    settings=dict(OTEL_EXPORTER_OTLP_TIMEOUT='1000')
    previous={key:os.environ.get(key) for key in settings};os.environ.update(settings)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-local-log-event-ids','independent-otlp-protobuf-deliveries','actual-collector-failures','native-task-receipts']))
    try:
        project=Path(json.loads(ADDON_TEMPLATE.read_text())['project_root'])
        sdk_roots=[project/'node_modules/@opentelemetry/sdk-logs',ADDON/'node_modules/@opentelemetry/sdk-logs']
        sources=[]
        for sdk in sdk_roots:
            if not (sdk/'package.json').is_file():continue
            for source in sdk.rglob('*.js'):
                if source.stat().st_size>1024**2:continue
                data=source.read_bytes()
                if b'maxQueueSize' in data and b'2048' in data and b'maxExportBatchSize' in data and b'512' in data:sources.append(dict(path=str(source),sha256=hashlib.sha256(data).hexdigest(),version=json.loads((sdk/'package.json').read_text())['version']))
        if not sources:raise RuntimeError('Installed official log SDK does not expose the registered default queue/batch limits')
        metadata['sdk_queue_contract_sources']=sources
        gateway=pilot.Gateway(root,configurer=lambda p:configure(p,count,token));gateway.ready()
        control=token+'_CONTROL';fixture.register(control);result=gateway.request(control);requests.append(result)
        if not result['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Native task control failed')
        # Controls emit only eight events; only the matched S04 target emits
        # the 4096-event burst against the unchanged native SDK defaults.
        if not wait_delivered(collector,'EVAL_OBS_EVENT_'+control+'_N'):raise RuntimeError('Official OTLP log publication positive control failed')
        row.update(native_invoked=True,fixture_validated=True)
        collector.fail=True;boundary=time.monotonic_ns();fixture.register(token)
        result=gateway.request(token);requests.append(result)
        deadline=time.monotonic()+8
        while time.monotonic()<deadline and not any(a.get('status')==503 and any(k.startswith(prefix) for k in a['ids']) for a in collector.attempts):time.sleep(.1)
        failures=[a for a in collector.attempts if a.get('status')==503 and any(k.startswith(prefix) for k in a['ids'])]
        if not failures:raise RuntimeError('Actual collector failure was not matched to target native event IDs')
        check('task-effect-independent-of-collector-failure',result['accepted'] and fixture.receipts.get(token)==1)
        if mode=='restart':
            os.killpg(gateway.process.pid,signal.SIGKILL);gateway.process.wait(timeout=5);gateway.stop()
            collector.fail=False;gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready()
            requests.extend(wait_control(gateway,fixture,token+'_POST_RESTART'))
        else:
            time.sleep(2 if mode=='brief' else 12 if mode=='long' else 3);collector.fail=False
        recovered=token+'_RECOVERY';fixture.register(recovered);result=gateway.request(recovered);requests.append(result)
        if not result['accepted'] or fixture.receipts.get(recovered)!=1:raise RuntimeError('Post-outage task control failed')
        if not wait_delivered(collector,'EVAL_OBS_EVENT_'+recovered+'_N'):raise RuntimeError('Post-outage OTLP publication control failed')
        time.sleep(3)
        native=(root/'gateway-native.log').read_text(errors='replace')
        expected=set(k for k in EVENT.findall(native) if k.startswith(prefix))
        if len(expected)!=count:raise RuntimeError('Native local log did not retain all offered unique target event IDs')
        delivered={k:v for k,v in collector.deliveries.items() if k in expected}
        missing=sorted(expected-set(delivered));duplicates=sum(max(0,n-1) for n in delivered.values())
        check('all-native-local-events-eventually-exported',not missing)
        check('no-duplicate-successful-collector-deliveries',duplicates==0)
        metadata.update(mode=mode,matching_failure_boundary_ns=boundary,offered_unique_events=count,
            missing_event_count=len(missing),duplicate_successful_deliveries=duplicates,event_id_prefix=prefix,
            native_local_event_indices=sorted(int(k.rsplit('_N',1)[1]) for k in expected),
            native_event_set_sha256=hashlib.sha256(json.dumps(sorted(expected)).encode()).hexdigest(),
            native_local_file_sha256=hashlib.sha256(native.encode()).hexdigest(),
            successful_deliveries_by_index={k.rsplit('_N',1)[1]:v for k,v in delivered.items()},
            missing_event_indices=[int(k.rsplit('_N',1)[1]) for k in missing],declared_sdk_environment=settings,
            sdk_default_queue_capacity=2048,sdk_default_batch_capacity=512,
            native_overflow_log_signal=bool(re.search(r'dropped|drop count|queue.*full|buffer.*full',native,re.I)),
            signal_scope='Native local file logs only; absence here does not prove absence from other diagnostic interfaces.',
            acceptance_scope='Lossless, nonduplicating delivery is the evaluation criterion, not an assumed durable-spool guarantee from the product. Synthetic content capture is explicitly enabled to independently join exact event IDs.',
            addon_version='2026.10.7',buffer_intervention='4096 synchronous target native log events offered against the unchanged SDK default 2048-entry queue in S04; controls emit eight. Native IDs and failed collector batches independently establish offered load.')
        attempts=[]
        for attempt in collector.attempts:
            groups={}
            for identifier in attempt.get('ids',[]):
                name,index=identifier.rsplit('_N',1);groups.setdefault(name,[]).append(int(index))
            attempts.append({**{k:v for k,v in attempt.items() if k!='ids'},'event_groups':groups})
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            metadata=metadata,requests=requests,collector_attempts=attempts,independent_receipts=fixture.receipts,
            resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2500],metadata=metadata)
    finally:
        collector.fail=False
        usage=shutil.disk_usage(pilot.BASE)
        row['owned_tmpfs_at_cleanup']=dict(total_bytes=usage.total,used_bytes=usage.used,free_bytes=usage.free)
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-4000:]
        collector.close();fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
        for key,value in previous.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
    return row
