"""Source-directed interventions; each changes one declared mechanism or fixture strategy."""

import concurrent.futures
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import threading
import time


def listener_owner(port=18789):
    inodes=set()
    for name in ['tcp','tcp6']:
        for line in Path('/proc/net/'+name).read_text().splitlines()[1:]:
            fields=line.split()
            if fields[3]=='0A' and int(fields[1].split(':')[-1],16)==port:
                inodes.add('socket:['+fields[9]+']')
    owners=set()
    for directory in Path('/proc').glob('[0-9]*/fd'):
        try:
            if any(os.readlink(path) in inodes for path in directory.iterdir()):
                owners.add(int(directory.parent.name))
        except OSError:
            pass
    if len(owners)!=1:
        raise RuntimeError('Cannot uniquely identify owned Gateway listener: '+str(sorted(owners)))
    return owners.pop()


class MainThreadProfiler:
    def __init__(self,pilot,gateway,label):
        self.process=None
        self.error=None
        self.owner_pid=listener_owner()
        try:
            opened=gateway.request('PILOT_PROFILE_'+label.upper().replace('-','_'))
            if not opened['accepted'] or listener_owner()!=self.owner_pid:
                raise RuntimeError('Inspector activation did not preserve the owned Gateway')
            self.process=subprocess.Popen([pilot.NODE,'/driver/profile.mjs'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
            if not select.select([self.process.stdout],[],[],5)[0]:
                raise RuntimeError('Inspector client readiness timeout')
            if not json.loads(self.process.stdout.readline()).get('ready'):
                raise RuntimeError('Inspector client not ready')
        except Exception as error:
            self.error=str(error)

    def command(self,method):
        if self.error:
            return dict(unavailable=self.error)
        try:
            self.process.stdin.write(json.dumps(dict(method=method))+'\n')
            self.process.stdin.flush()
            if not select.select([self.process.stdout],[],[],15)[0]:
                raise RuntimeError('Inspector response timeout')
            return json.loads(self.process.stdout.readline())
        except Exception as error:
            self.error=str(error)
            return dict(unavailable=self.error)

    def close(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.stdin.write('{"method":"close"}\n')
                self.process.stdin.flush()
                self.process.wait(timeout=2)
            except (OSError,subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait()


def cpu_delta(before,after):
    return dict(user_seconds=after['user_seconds']-before['user_seconds'],
                system_seconds=after['system_seconds']-before['system_seconds'],
                window_ms=(after['monotonic_ns']-before['monotonic_ns'])/1e6,
                scope='Live/previously sampled Gateway descendants inside this batch window; excludes startup. Short-lived unsampled processes can be missed.')


def provider_totals(events):
    requests=[e for e in events if e['kind']=='provider-request']
    counts={t:sum(e['token']==t for e in requests) for t in {e['token'] for e in requests}}
    return dict(model_requests=len(requests),requests_per_task=counts,
                total_payload_bytes=sum(e['payload_bytes'] for e in requests),
                total_tool_schema_bytes=sum(e['tool_schema_bytes'] for e in requests),
                total_message_bytes=sum(e['message_bytes'] for e in requests),
                first_tool_schema_count=len(requests[0]['tool_names']) if requests else 0,
                first_tool_names=requests[0]['tool_names'][:8] if requests else [],
                token_counts=None,calculated_cost_usd=None,
                limitation='Wire/schema/message bytes and request counts are not token counts or provider charges.')


def compact_request(request):
    return {key:value for key,value in request.items() if key!='response_excerpt'}


def observe_natural_exit(process,timeout=1):
    """Wait without signalling: a fast poll can still see an owner finishing exit."""
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


def checkpoint(study,arm,planned):
    print(json.dumps(dict(kind='arm-checkpoint',product='openclaw',study=study,planned_arms=planned,arm=arm),ensure_ascii=False,separators=(',',':')),flush=True)


def batch(pilot,fixture,gateway,label,profile=False):
    profiler=MainThreadProfiler(pilot,gateway,label) if profile else None
    start_profile=profiler.command('start') if profiler else None
    tokens=['PILOT_SRC_'+label.upper().replace('-','_')+'_T'+str(i) for i in range(8)]
    barrier=threading.Barrier(8)
    def request(token):
        barrier.wait()
        return gateway.request(token)
    start=len(fixture.events)
    before=gateway.sampler.snapshot()
    began=time.monotonic()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(request,tokens))
        elapsed=time.monotonic()-began
        after=gateway.sampler.snapshot()
        profile_result=profiler.command('stop') if profiler else None
    finally:
        if profiler:
            profiler.close()
    events=fixture.events[start:]
    counts={token:sum(e['kind']=='effect-commit' and e.get('token')==token for e in events) for token in tokens}
    correct=sum(r['accepted'] and counts[r['token']]==1 for r in results)
    return dict(attempts=8,accepted=correct,response_completion_markers=sum(r['accepted'] for r in results),seconds=elapsed,
                correct_goodput_per_s=correct/elapsed,
                requests=[compact_request(r) for r in results],effect_counts=counts,
                actual_effect_overlap=pilot.peak_overlap(events),provider=provider_totals(events),
                batch_cpu=cpu_delta(before,after),profile_start=start_profile,main_thread_profile=profile_result,
                main_thread_profile_owner=profiler.owner_pid if profiler else None,
                native_evidence=pilot.native_evidence(gateway.root,tokens),
                effect_timeline=[e for e in events if e['kind'] in {'effect-start','effect-commit'}],
                task_contract_ok=correct==8,
                valid=len(results)==8 and elapsed>0)


def denied_control(fixture,gateway,label):
    start=len(fixture.events)
    alive=gateway.process.poll() is None
    response=gateway.request('PILOT_DENIED_'+label.upper().replace('-','_'))
    events=fixture.events[start:]
    effects=sum(e['kind']=='effect-commit' for e in events)
    return dict(response=compact_request(response),effect_count=effects,
                rejected_without_effect=not response['accepted'] and effects==0,
                valid=alive and any(e['kind']=='provider-request' for e in events),
                scope='A registered synthetic tool excluded by tools.allow; a model explicitly requests its ID/name. This is one allowlist control, not a complete security assessment.')


def workload_study(pilot,fixture,blocks,scheduling=False):
    arms=[]
    if scheduling:
        conditions=[dict(label='short-c1',cap=1,delay=150),dict(label='short-c4',cap=4,delay=150),
                    dict(label='long-c1',cap=1,delay=1500),dict(label='long-c4',cap=4,delay=1500)]
    else:
        conditions=[dict(label='discover-small',strategy='conservative',catalog=1,search=None),
                    dict(label='known-small',strategy='known',catalog=1,search=None),
                    dict(label='known-large',strategy='known',catalog=64,search=None),
                    dict(label='direct-large',strategy='known',catalog=64,search=False)]
    for block in range(blocks):
        for condition in (conditions if block%2==0 else list(reversed(conditions))):
            label=('schedule' if scheduling else 'catalog')+f'-b{block}-'+condition['label']
            root=pilot.BASE/label
            root.mkdir()
            fixture.strategy='known' if scheduling else condition['strategy']
            fixture.effect_delay_ms=condition['delay'] if scheduling else 150
            gateway=pilot.Gateway(root,concurrency=condition.get('cap',4),catalog_size=condition.get('catalog',1),tool_search=condition.get('search'))
            try:
                gateway.ready()
                warm=gateway.request('PILOT_WARM_'+label.upper().replace('-','_'))
                if not warm['accepted']:
                    raise RuntimeError('Source study warmup failed: '+json.dumps(warm)+' '+''.join(gateway.log_tail)[-1200:])
                measured=batch(pilot,fixture,gateway,label,profile=scheduling)
                denied=denied_control(fixture,gateway,label)
                arms.append(dict(block=block,condition=condition,measurements=measured,denied_control=denied,
                                 startup_and_run_resources=gateway.sampler.summary(),state=pilot.allocation(root),
                                 native_effective_config=pilot.effective_config(root),
                                 valid=measured['valid'] and denied['valid']))
            finally:
                gateway.stop()
                shutil.rmtree(root)
            checkpoint('SRC-02' if scheduling else 'SRC-01',arms[-1],len(conditions)*blocks)
    return dict(study='SRC-02' if scheduling else 'SRC-01',status='source-directed-executed',
                independent_blocks=blocks,arms=arms,valid=all(a['valid'] for a in arms),
                contrasts=['cap 1 versus 4 within each declared effect delay; short versus long delay within each cap'] if scheduling else
                          ['conservative versus known-name catalog: fixture strategy changes, not an OpenClaw architectural ablation',
                           'known small versus known large: authorized catalog size changes',
                           'known large versus direct large: native tools.toolSearch configuration changes'],
                limitations=['All responses are deterministic; no real-model reasoning, actual token bill or population performance estimate.',
                             'Batch CPU excludes startup; cumulative resource samples retain their separate wider scope.',
                             'V8 profiling, when requested, is diagnostic instrumentation; bundle regions are not source-map line proof.'])


def failure_study(pilot,fixture,blocks):
    (pilot.BASE/'source-owned-canary').write_text('SYNTHETIC_SOURCE_CANARY')
    fixture.strategy='known'
    fixture.effect_delay_ms=150
    arms=[]
    for block in range(blocks):
        for route in (['plugin','mcp'] if block%2==0 else ['mcp','plugin']):
            root=pilot.BASE/f'failure-b{block}-{route}'
            root.mkdir()
            gateway=pilot.Gateway(root,route=route)
            try:
                gateway.ready()
                owner=listener_owner()
                warm=gateway.request(f'PILOT_WARM_B{block}_{route.upper()}')
                if not warm['accepted']:
                    raise RuntimeError('Failure-study positive control failed')
                start=len(fixture.events)
                canary=gateway.request(f'PILOT_CANARY_B{block}_{route.upper()}')
                thrown=gateway.request(f'PILOT_THROW_B{block}_{route.upper()}')
                after_throw=gateway.request(f'PILOT_PLAIN_THROW_B{block}_{route.upper()}')
                owner_after_throw=listener_owner() if gateway.process.poll() is None else None
                crashed=gateway.request(f'PILOT_CRASH_B{block}_{route.upper()}') if owner_after_throw else dict(accepted=False,not_run='Gateway ended after throw')
                natural_exit=observe_natural_exit(gateway.process)
                after_crash=gateway.request(f'PILOT_PLAIN_CRASH_B{block}_{route.upper()}') if gateway.process.poll() is None else None
                alive=gateway.process.poll() is None
                events=fixture.events[start:]
                canary_events=[e for e in events if e['kind']=='effect-start' and '_CANARY_' in e['token']]
                canary_entered=[e for e in events if e['kind']=='fault-start' and e.get('action')=='canary']
                throw_events=[e for e in events if e['kind']=='fault-start' and e.get('action')=='throw']
                crash_events=[e for e in events if e['kind']=='fault-start' and e.get('action')=='crash']
                arms.append(dict(block=block,route=route,gateway_owner_pid=owner,
                    canary=compact_request(canary),canary_events=canary_events,canary_entry_markers=canary_entered,
                    throw_response=thrown,neighbor_after_throw=compact_request(after_throw),owner_after_throw=owner_after_throw,
                    crash_response=compact_request(crashed),neighbor_after_crash=compact_request(after_crash) if after_crash else None,
                    gateway_alive_after_crash=alive,gateway_exit_code=gateway.process.poll(),
                    natural_exit_code=natural_exit,natural_settlement_window_seconds=1,
                    throw_markers=throw_events,crash_markers=crash_events,resources=gateway.sampler.summary(),
                    native_log_tail=list(gateway.log_tail)[-8:],
                    valid=bool(canary_entered) and bool(throw_events)
                          and (bool(crash_events) or owner_after_throw is None)))
            finally:
                gateway.stop()
                shutil.rmtree(root)
            checkpoint('SRC-03',arms[-1],2*blocks)
    return dict(study='SRC-03',status='source-directed-executed',independent_blocks=blocks,arms=arms,
                valid=all(a['valid'] for a in arms),
                limitations=['Trusted synthetic code reading an explicitly owned accessible canary; not a bypass of a declared permission.',
                             'A caught exception and process termination have different owners; no general malicious-plugin safety claim.'])


def scope_study(pilot,fixture,blocks):
    server=pilot.OwnedSSH()
    fixture.strategy='known'
    arms=[]
    try:
        for block in range(blocks):
            for scope in (['agent','session'] if block%2==0 else ['session','agent']):
                root=pilot.BASE/f'scope-source-b{block}-{scope}'
                root.mkdir()
                gateway=pilot.Gateway(root,sandbox_scope=scope,ssh_backend=True)
                try:
                    gateway.ready()
                    write=gateway.request(f'PILOT_SANDBOX_WRITE_B{block}_{scope.upper()}',session_key='source-writer')
                    files=list((root/'remote').rglob('scope-canary.txt'))
                    if not write['accepted'] or len(files)!=1:
                        raise RuntimeError('Scope writer control failed')
                    start=len(fixture.events)
                    # Both named sessions use the same explicit SSH target/identity.
                    # The source fixture only reads this known synthetic sibling file.
                    original=pilot.target_arguments
                    sibling=str(files[0])
                    def args(token,action):
                        if '_CROSS_' not in token:
                            return original(token,action)
                        import shlex
                        code="import pathlib,json; p=pathlib.Path("+repr(sibling)+"); print('CROSS:'+json.dumps({'readable':p.read_text()=='SYNTHETIC_SCOPE_CANARY'})); print('RECEIPT:'+"+repr(token)+")"
                        return dict(command='python3 -c '+shlex.quote(code),yieldMs=10000)
                    pilot.target_arguments=args
                    try:
                        relative=gateway.request(f'PILOT_SANDBOX_READ_B{block}_{scope.upper()}',session_key='source-reader')
                        cross=gateway.request(f'PILOT_SANDBOX_CROSS_B{block}_{scope.upper()}',session_key='source-reader')
                    finally:
                        pilot.target_arguments=original
                    events=fixture.events[start:]
                    arms.append(dict(block=block,scope=scope,writer=compact_request(write),relative_read=compact_request(relative),
                                     explicit_sibling_read=compact_request(cross),
                                     native_results=[e for e in events if e['kind']=='tool-result'],
                                     canary_relative_path=str(files[0].relative_to(root)),
                                     native_effective_config=pilot.effective_config(root),state=pilot.allocation(root),resources=gateway.sampler.summary(),
                                     valid=write['accepted'] and relative['accepted'] and any(e['kind']=='tool-result' and '_CROSS_' in e.get('token','') for e in events)))
                finally:
                    gateway.stop()
                    shutil.rmtree(root)
                checkpoint('SRC-04',arms[-1],2*blocks)
    finally:
        server.stop()
    return dict(study='SRC-04',status='source-directed-executed',independent_blocks=blocks,arms=arms,
                valid=all(a['valid'] for a in arms),
                limitations=['Scope selects workspace identity; this owned SSH deployment deliberately shares one OS principal.',
                             'Explicit sibling-file readability is a deployment/authority-boundary observation, not a claim that directory scope promised hostile-tenant isolation.'])


def run(pilot,fixture,blocks,selection,output):
    functions={'SRC-01':lambda:workload_study(pilot,fixture,blocks),
               'SRC-02':lambda:workload_study(pilot,fixture,blocks,scheduling=True),
               'SRC-03':lambda:failure_study(pilot,fixture,blocks),
               'SRC-04':lambda:scope_study(pilot,fixture,blocks)}
    for identifier in list(functions) if selection=='source-followup' else [selection]:
        output.append(functions[identifier]())
