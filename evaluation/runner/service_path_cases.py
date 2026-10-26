"""Bounded public-Gateway service-path, initialization and owned-disk experiments.

These are mechanism measurements with a scripted provider, never model quality
or monetary cost measurements. Every comparison retains both native arms.
"""
import concurrent.futures
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import shutil
import threading
import time

import hook_cases
import mechanism_cases as mechanism
import pilot

FAMILIES = {
    'PERF-01': ['catalogue', 'history', 'component-cache'],
    'PERF-02': ['cpu', 'io', 'one-session', 'independent-sessions'],
    'PERF-04': ['slow-tool', 'large-preparation', 'short-burst', 'cancel-slow'],
    'COST-02': ['cold-cache', 'warm-cache', 'warm-process', 'plugin-reload'],
    'COST-04': ['one-run', 'many-runs', 'interrupted-startup', 'cleanup'],
}
SCENARIOS = {f'{family}-S{i:02}': mode for family, modes in FAMILIES.items() for i, mode in enumerate(modes, 1)}


class InstrumentedFixture(mechanism.MechanismFixture):
    """Observe native provider input without modifying the request or transcript."""
    def handler(self):
        base=super().handler(); owner=self
        class Handler(base):
            def do_POST(self):
                if self.path.endswith('/chat/completions'):
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=4*1024**2:return self.send(dict(error='fixture-bound'),413)
                    raw=self.rfile.read(size); body=json.loads(raw)
                    owner.event('provider-input-shape',request_bytes=size,
                        messages_bytes=len(json.dumps(body.get('messages',[])).encode()),
                        messages_count=len(body.get('messages',[])),
                        tool_catalogue_bytes=len(json.dumps(body.get('tools',[])).encode()),
                        tool_catalogue_count=len(body.get('tools',[])))
                    original=self.rfile; self.rfile=io.BytesIO(raw)
                    try:return super().do_POST()
                    finally:self.rfile=original
                return super().do_POST()
        return Handler


def configure(root, catalogue=1):
    config = mechanism.configure(root, 'PERF-06-S01')
    plugin = root/'composition-a/index.js'
    source = plugin.read_text().replace("if(args.action==='cpu'){", "if(args.action==='wait')await new Promise(resolve=>setTimeout(resolve,600));\n  if(args.action==='cpu'){")
    # Schemas and executable registrations both exist. A catalogue manifest alone
    # would not establish the native request-preparation workload.
    padding = ['padding_'+str(i) for i in range(catalogue-1)]
    extra = '\n'.join('api.registerTool('+json.dumps(dict(name=name, description='Synthetic schema padding. '*16,
        parameters=dict(type='object', properties=dict(value=dict(type='string', description='Schema field. '*32)))))[:-1]+
        ",async execute(){return {content:[{type:'text',text:'unused'}]};}});" for name in padding)
    source = source.replace(" const owner=__ID__;", " const owner=__ID__;")  # IDs are already substituted by the fixture.
    source = source.replace(" const owner=\"composition-a\";", " const owner=\"composition-a\";\n"+extra)
    plugin.write_text(source)
    manifest = json.loads((root/'composition-a/openclaw.plugin.json').read_text())
    manifest['contracts']['tools'].extend(padding)
    pilot.save(root/'composition-a/openclaw.plugin.json', manifest)
    config['tools']['allow'].extend(padding)
    pilot.save(root/'config.json', config)
    return config


def reuse(root):
    return json.loads((root/'config.json').read_text())


def thread_counters(pid):
    rows = []
    ticks = os.sysconf('SC_CLK_TCK')
    for path in Path('/proc', str(pid), 'task').glob('*/stat'):
        try:
            text = path.read_text(); values = text[text.rfind(')')+2:].split()
            schedule = [int(v) for v in (path.parent/'schedstat').read_text().split()]
            rows.append(dict(tid=int(path.parent.name), name=text[text.find('(')+1:text.rfind(')')],
                user_seconds=int(values[11])/ticks, system_seconds=int(values[12])/ticks,
                running_ns=schedule[0], runqueue_ns=schedule[1]))
        except (OSError, ValueError):
            continue
    return rows


class Responsiveness:
    """Independent /readyz service progress and native thread CPU/runqueue samples."""
    def __init__(self, pid):
        self.pid=pid; self.done=threading.Event(); self.samples=[]
        self.thread=threading.Thread(target=self.sample, daemon=True); self.thread.start()

    def sample(self):
        while not self.done.is_set():
            start=time.monotonic_ns(); connection=http.client.HTTPConnection('127.0.0.1',18789,timeout=2)
            status=None
            try:
                connection.request('GET','/readyz'); response=connection.getresponse(); response.read(4096); status=response.status
            except (OSError,http.client.HTTPException):
                pass
            finally:
                connection.close()
            self.samples.append(dict(monotonic_ns=start, latency_ms=(time.monotonic_ns()-start)/1e6,
                http_status=status, threads=thread_counters(self.pid)))
            self.done.wait(.05)

    def stop(self):
        self.done.set(); self.thread.join(timeout=3)
        # Thread boundary counters and distribution are sufficient for retained
        # evidence; an unbounded per-thread 50 ms dump would amplify storage.
        latencies=sorted(s['latency_ms'] for s in self.samples)
        return dict(samples=len(self.samples), successful_probes=sum(s['http_status']==200 for s in self.samples),
            probe_latency_ms=dict(median=latencies[len(latencies)//2] if latencies else None,
                maximum=max(latencies,default=None)), first=self.samples[0] if self.samples else None,
            last=self.samples[-1] if self.samples else None,
            limitation='50 ms sampled Gateway threads; exited threads can be missed. /readyz measures service progress, not agent first-text latency.')


def owned_inventory(root, pid=None):
    files=[]; directories=0; deleted=[]
    for path in root.rglob('*'):
        if path.is_symlink():
            continue
        if path.is_dir(): directories+=1
        elif path.is_file():
            stat=path.stat(); files.append(dict(path=str(path.relative_to(root)), bytes=stat.st_size, blocks=stat.st_blocks))
    if pid:
        for member in mechanism.process_snapshot(pid)['pids']:
            for descriptor in Path('/proc',str(member),'fd').glob('*'):
                try:
                    target=os.readlink(descriptor)
                    if target.startswith(str(root)+'/') and target.endswith(' (deleted)'):
                        stat=descriptor.stat(); deleted.append(dict(pid=member,fd=descriptor.name,bytes=stat.st_size,blocks=stat.st_blocks))
                except OSError:
                    continue
    return dict(apparent_bytes=sum(f['bytes'] for f in files), allocated_bytes=sum(f['blocks']*512 for f in files),
        file_inodes=len(files), directory_inodes=directories, open_deleted=deleted,
        files_sha256=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),
        ownership_root=str(root), shared_runtime_included=False,
        cache_scope='Shared installation is read-only and excluded; run-owned JITI cache is reported separately.')


def run_scenario(root, scenario, unit=1):
    family=scenario.rsplit('-S',1)[0]; mode=SCENARIOS[scenario]
    token='PILOT_PATH_'+scenario.replace('-','_')+'_U'+str(unit)
    fixture=InstrumentedFixture(); gateway=None; monitor=None
    observation=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    arms=[]; assertions=[]; measured=[]
    def check(name,condition,evidence=('native-arms','independent-events')):
        assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=list(evidence)))
    def register(label,**kwargs):
        item=token+'_'+label; fixture.register(item,**kwargs); measured.append(item); return item
    def start(path,catalogue=1,existing=False):
        nonlocal gateway
        before=time.monotonic_ns()
        gateway=pilot.Gateway(path,configurer=reuse if existing else lambda p:configure(p,catalogue))
        gateway.ready()
        return (time.monotonic_ns()-before)/1e6
    def request(item,session=None):
        return gateway.request(item,session_key=session)
    def arm(label,items,parallel=False,session=None):
        nonlocal monitor
        begin=len(fixture.events); before=mechanism.process_snapshot(gateway.process.pid)
        monitor=Responsiveness(gateway.process.pid); started=time.monotonic_ns()
        if parallel:
            results=mechanism.wave(gateway,fixture,items,same_session=bool(session))
        else:
            results=[request(item,session) for item in items]
        elapsed=(time.monotonic_ns()-started)/1e6
        progress=monitor.stop(); monitor=None
        events=fixture.events[begin:]
        requests=[{k:v for k,v in r.items() if k!='response_excerpt'} for r in results]
        first_provider={item:min((e['monotonic_ns'] for e in events if e['kind']=='provider-request' and e.get('token')==item),default=None) for item in items}
        row=dict(label=label,wall_ms=elapsed,requests=requests,events=events,
            first_provider_monotonic_ns=first_provider,process_before=before,
            process_after=mechanism.process_snapshot(gateway.process.pid),service_progress=progress,
            disk=owned_inventory(gateway.root,gateway.process.pid),resources=gateway.sampler.summary())
        arms.append(row)
        return row
    try:
        startup=start(root/'primary',128 if family=='PERF-04' and mode=='large-preparation' else 1)
        control=register('CONTROL'); positive=request(control)
        if not positive['accepted'] or fixture.receipts.get(control)!=1:
            raise RuntimeError('Independent native receipt positive control failed: '+json.dumps(positive)[:1200])
        observation.update(native_invoked=True,fixture_validated=True)
        metadata=dict(initial_startup_ms=startup,shared_installation_copied=False,paid_model_calls=0,
            timing='HTTP completion, independent provider/tool/effect monotonic events, /readyz probes and native per-thread CPU/runqueue counters. First text is not exposed by these non-streamed requests and remains unmeasured.')
        if family=='PERF-01':
            if mode=='catalogue':
                arm('one-tool',[register('SMALL')]); gateway.stop()
                metadata['large_startup_ms']=start(root/'large',128)
                arm('128-tools',[register('LARGE')]); metadata['catalogue_sizes']=[1,128]
            elif mode=='history':
                session=token.lower()+'_history'
                arm('short-history',[register('SHORT')],session=session)
                history=[register('HISTORY'+str(i)) for i in range(12)]
                arm('twelve-history-turns',history,session=session)
                arm('long-history',[register('LONG')],session=session)
                metadata['history_condition']='Same native session, twelve real tool/result turns retained before the long-history request; no direct state edits.'
            else:
                gateway.stop(); shutil.rmtree(pilot.BASE/'cache',ignore_errors=True); (pilot.BASE/'cache').mkdir()
                metadata['cold_startup_ms']=start(root/'cold')
                arm('cold-component-cache',[register('COLD')]); gateway.stop()
                metadata['warm_startup_ms']=start(root/'warm')
                arm('warm-component-cache',[register('WARM')])
        elif family=='PERF-02':
            if mode in {'cpu','io'}:
                arm('baseline',[register('BASE')])
                action='cpu' if mode=='cpu' else 'wait'
                arm(mode,[register('INTERVENTION',action=action)])
                metadata['intervention']='600 ms native plugin synchronous CPU loop' if mode=='cpu' else '600 ms native plugin asynchronous timer, same receipt operation'
            else:
                items=[register('T'+str(i),delay=.1) for i in range(6)]
                arm(mode,items,parallel=mode=='independent-sessions',session=token.lower() if mode=='one-session' else None)
                metadata['session_condition']='Six ordered turns in one session' if mode=='one-session' else 'Six simultaneously offered independent sessions'
        elif family=='PERF-04':
            slow=register('SLOW',delay=.8,gate=mode=='cancel-slow'); short=[register('SHORT'+str(i)) for i in range(8 if mode=='short-burst' else 2)]
            if mode=='cancel-slow':fixture.release.clear()
            begin=len(fixture.events); monitor=Responsiveness(gateway.process.pid)
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
                pending=pool.submit(request,slow)
                reached=mechanism.wait_events(fixture,'effect-start',[slow])
                if not reached: raise RuntimeError('Slow task failed to reach matched intervention boundary')
                cancellation=None
                if mode=='cancel-slow':
                    metadata['cancel_boundary']=dict(request_pending_before_rpc=not pending.done(),
                        rpc_started_monotonic_ns=time.monotonic_ns())
                    cancellation=hook_cases.rpc(gateway,'sessions.abort',dict(key='agent:main:pilot:'+slow.lower()))
                    metadata['cancel_boundary']['rpc_returned_monotonic_ns']=time.monotonic_ns()
                    fixture.release.set()
                    metadata['cancel_boundary']['external_gate_released_monotonic_ns']=time.monotonic_ns()
                results=list(pool.map(request,short)); slow_result=pending.result(timeout=40)
            progress=monitor.stop(); monitor=None
            arms.append(dict(label=mode,requests=[{k:v for k,v in r.items() if k!='response_excerpt'} for r in [slow_result,*results]],
                events=fixture.events[begin:],service_progress=progress,resources=gateway.sampler.summary(),cancellation=cancellation))
            check('short-tasks-finish-during-slow-work',all(r['accepted'] for r in results))
            if mode=='cancel-slow':
                check('native-cancellation-accepted',cancellation['returncode']==0)
                native_abort=json.loads(cancellation['stdout'])
                check('cancellation-targeted-an-actually-active-run',metadata['cancel_boundary']['request_pending_before_rpc'] and isinstance(native_abort.get('abortedRunId'),str))
                check('cancelled-task-not-falsely-completed',not slow_result['accepted'])
                metadata['effect_after_abort']='The uncooperative external service may still commit; its receipt is recorded independently.'
            else:check('slow-task-completes',slow_result['accepted'])
        elif family=='COST-02':
            if mode in {'cold-cache','warm-cache'}:
                gateway.stop()
                if mode=='cold-cache':
                    shutil.rmtree(pilot.BASE/'cache',ignore_errors=True); (pilot.BASE/'cache').mkdir()
                metadata['measured_startup_ms']=start(root/mode)
                arm(mode,[register('TASK')])
            elif mode=='warm-process':
                arm('first-turn',[register('FIRST')]); arm('same-process-later-turn',[register('LATER')])
            else:
                for index in range(3):
                    if index:
                        gateway.stop(); metadata['reload_startup_ms_'+str(index)]=start(root/'primary',existing=True)
                    arm('load-'+str(index),[register('LOAD'+str(index))])
            metadata['reuse_manifest']=dict(runtime_version_held_fixed=True,workspace_and_plugin_sources_held_fixed=True,
                compile_cache_disabled=True,jiti_cache='Only the run-owned /scratch/cache/jiti; cold arm removes it, warm arm preserves it.',
                process_generation_reused=mode=='warm-process',plugin_registration_repeated=mode=='plugin-reload')
        else:
            before=owned_inventory(root,gateway.process.pid)
            if mode=='interrupted-startup':
                gateway.stop(); gateway=pilot.Gateway(root/'interrupted',configurer=configure)
                time.sleep(.2); os.killpg(gateway.process.pid,9); gateway.process.wait(timeout=5); gateway.stop()
                metadata['interrupted_generation']=dict(exit_code=gateway.process.returncode,delay_after_spawn_ms=200,
                    scope='Native Gateway startup/config/state setup; not package download or installer publication.')
                start(root/'interrupted',existing=True)
                arm('restart-after-interruption',[register('RECOVER')])
            else:
                arm(mode,[register('T'+str(i)) for i in range(12 if mode=='many-runs' else 1)])
            metadata['disk_before']=before; metadata['disk_before_cleanup']=owned_inventory(root,gateway.process.pid)
            gateway.stop()
            metadata['disk_after_stop']=owned_inventory(root)
            retained=json.dumps(dict(scenario_id=scenario,events_sha256=hashlib.sha256(json.dumps(fixture.events).encode()).hexdigest(),
                native_records=pilot.native_evidence(gateway.root,measured)),separators=(',',':')).encode()
            metadata['retained_evidence_bytes']=len(retained); metadata['retained_evidence_sha256']=hashlib.sha256(retained).hexdigest()
            shutil.rmtree(root)
            metadata['disk_after_cleanup']=dict(apparent_bytes=0,allocated_bytes=0,file_inodes=0,directory_inodes=0,root_exists=root.exists())
            check('owned-root-removed-after-retaining-evidence',not root.exists(),('ownership-manifest','disk-inventory'))
            metadata['cache_inventory']=owned_inventory(pilot.BASE/'cache')
        for row in arms:
            for result in row['requests']:
                if family=='PERF-04' and mode=='cancel-slow' and result['token'].endswith('_SLOW'):continue
                check('accepted-'+result['token'],result['accepted'])
        check('no-duplicate-independent-effects',all(fixture.receipts.get(item,0)<=1 for item in measured))
        if not (family=='PERF-04' and mode=='cancel-slow'):
            check('all-offered-tasks-have-exactly-one-receipt',all(fixture.receipts.get(item)==1 for item in measured))
        observation.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            arms=arms,metadata=metadata,independent_receipts=fixture.receipts,
            usage_note='Scripted local provider. Token price and model quality are not measured.')
    except Exception as error:
        observation.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2500],arms=arms)
    finally:
        fixture.release.set()
        if monitor:monitor.stop()
        if gateway:gateway.stop()
        fixture.close(); shutil.rmtree(root,ignore_errors=True)
        observation['owned_state_retained']=root.exists()
    return observation
