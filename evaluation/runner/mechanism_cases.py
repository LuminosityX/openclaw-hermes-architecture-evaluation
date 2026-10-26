"""Bounded native load, resource and plugin-composition experiments.

The provider is a deterministic local fixture. Outcomes come from independently
committed receipts, not the provider's final text. No real model ability or
provider cost is measured here. The same adapters can later execute frozen units.
"""
import concurrent.futures
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import threading
import time

import pilot
import hook_cases


FAMILIES = {
    'PERF-05': ['steady', 'burst', 'slow-service', 'recovery'],
    'PERF-06': ['independent-sessions', 'shared-session', 'long-transaction', 'delayed-commit'],
    'COST-01': ['idle', 'one-session', 'four-sessions', 'sixteen-sessions', 'drained'],
    'COST-06': ['idle', 'one-task', 'concurrency-sweep', 'cpu-pressure', 'io-network', 'cancel-cleanup'],
    'EXT-09': ['coexist', 'collision', 'config', 'dependencies', 'failure-during-task'],
}
SCENARIOS = {f'{family}-S{i:02}': mode for family, modes in FAMILIES.items() for i, mode in enumerate(modes, 1)}

PLUGIN = r'''
import fs from 'node:fs';
import {version as dependencyVersion} from 'eval-private-dependency';
export default {id:__ID__,name:__ID__,register(api){
 const owner=__ID__;
 api.registerTool({name:__TOOL__,description:'Synthetic independently receipted bounded evaluation operation',
 parameters:{type:'object',properties:{token:{type:'string'},action:{type:'string'}},required:['token']},
 async execute(id,args){
  const announce=async(path,extra={})=>{
   const r=await fetch('http://127.0.0.1:18080/'+path,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({token:args.token,owner,pid:process.pid,dependency_version:dependencyVersion,config_tag:api.pluginConfig?.tag,...extra})});
   if(!r.ok)throw new Error('EVAL_FIXTURE_HTTP_'+r.status);
   return await r.json();
  };
  await announce('entered');
  if(args.action==='throw')throw new Error('EVAL_COMPOSITION_TOOL_FAILURE');
  if(args.action==='cpu'){
   const begin=performance.now();let x=0;
   while(performance.now()-begin<600)x=Math.imul(x+1,48271);
   await announce('work',{cpu_loop_ms:performance.now()-begin,checksum:x});
  }
  if(args.action==='io'){
   const file=__ROOT__+'/io-'+args.token;
   const payload=Buffer.alloc(256*1024,97);fs.writeFileSync(file,payload);
   const data=fs.readFileSync(file);fs.unlinkSync(file);
   await announce('work',{file_write_bytes:payload.length,file_read_bytes:data.length});
   const r=await fetch('http://127.0.0.1:18080/bytes');
   const bytes=await r.arrayBuffer();await announce('work',{http_payload_read_bytes:bytes.byteLength});
  }
  const receipt=await announce('effect');
  return {content:[{type:'text',text:JSON.stringify(receipt)}]};
 }});
}};
'''


def write_plugin(root, identifier, tool, dependency='1.0.0'):
    directory = root/identifier
    directory.mkdir()
    pilot.save(directory/'package.json', dict(name=identifier, version='1.0.0', type='module',
        openclaw=dict(extensions=['./index.js']), dependencies={'eval-private-dependency': dependency}))
    pilot.save(directory/'openclaw.plugin.json', dict(id=identifier, activation=dict(onStartup=True),
        contracts=dict(tools=[tool]), configSchema=dict(type='object', additionalProperties=False,
            properties=dict(tag=dict(type='string')))))
    dep = directory/'node_modules/eval-private-dependency'
    dep.mkdir(parents=True)
    pilot.save(dep/'package.json', dict(name='eval-private-dependency', version=dependency, type='module', exports='./index.js'))
    (dep/'index.js').write_text('export const version='+json.dumps(dependency)+';\n')
    (directory/'index.js').write_text(PLUGIN.replace('__ID__', json.dumps(identifier)).replace('__TOOL__', json.dumps(tool)).replace('__ROOT__', json.dumps(str(root))))
    return directory


def configure(root, scenario):
    family = scenario.rsplit('-S', 1)[0]
    mode = SCENARIOS[scenario]
    config = pilot.configuration(root, concurrency=2 if family == 'PERF-05' else 16, tool_search=False)
    shutil.rmtree(root/'plugin')
    tools = ['eval_probe']
    names = ['composition-a']
    paths = [write_plugin(root, names[0], tools[0])]
    entries = {names[0]: dict(enabled=True, config=dict(tag='CONFIG_A'))}
    if family == 'EXT-09':
        names.append('composition-b')
        second_tool = 'eval_probe' if mode == 'collision' else 'eval_other'
        paths.append(write_plugin(root, names[1], second_tool, '2.0.0' if mode == 'dependencies' else '1.0.0'))
        entries[names[1]] = dict(enabled=True, config=dict(tag='CONFIG_B'))
        tools.append(second_tool)
        if mode == 'collision':
            names.append('composition-control')
            paths.append(write_plugin(root, names[-1], 'eval_control'))
            entries[names[-1]] = dict(enabled=True, config=dict(tag='CONTROL'))
            tools.append('eval_control')
    config['plugins'] = dict(allow=names, load=dict(paths=[str(p) for p in paths]), entries=entries)
    config['tools']['allow'] = list(dict.fromkeys(tools))
    pilot.save(root/'config.json', config)
    return config


class MechanismFixture(pilot.Fixture):
    def __init__(self):
        self.tasks = {}
        self.receipts = {}
        self.release = threading.Event()
        self.release.set()
        self.transmit_bytes = 0
        self.receive_bytes = 0
        super().__init__()

    def register(self, token, tool='eval_probe', action='effect', delay=0, gate=False, fail=False, response_delay=0):
        self.tasks[token] = dict(tool=tool, action=action, delay=delay, gate=gate, fail=fail, response_delay=response_delay)

    def handler(self):
        base = super().handler()
        owner = self
        class Handler(base):
            def send(self, data, status=200):
                owner.transmit_bytes += len(json.dumps(data).encode())
                return super().send(data, status)

            def do_GET(self):
                if self.path != '/bytes':
                    return super().do_GET()
                payload = b'e'*(256*1024)
                owner.transmit_bytes += len(payload)
                owner.event('network-payload', bytes=len(payload))
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self):
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4*1024**2:
                    return self.send(dict(error='fixture-request-bound'), 413)
                raw = self.rfile.read(size)
                owner.receive_bytes += len(raw)
                body = json.loads(raw)
                if self.path in {'/entered', '/work', '/effect'}:
                    token = body.get('token')
                    if token not in owner.tasks:
                        return self.send(dict(error='unregistered-task'), 400)
                    if self.path != '/effect':
                        owner.event('tool-entered' if self.path == '/entered' else 'tool-work', **body)
                        return self.send(dict(recorded=True))
                    task = owner.tasks[token]
                    owner.event('effect-start', **body)
                    if task['gate']:
                        released = owner.release.wait(timeout=12)
                        if not released:
                            owner.event('fixture-gate-timeout', token=token)
                            return self.send(dict(error='fixture-gate-timeout'), 504)
                    if task['delay']:
                        time.sleep(task['delay'])
                    with owner.lock:
                        count = owner.receipts.get(token, 0)+1
                        owner.receipts[token] = count
                    receipt = 'RECEIPT:'+token
                    owner.event('effect-commit', **body, ordinal=count, receipt=receipt)
                    if task['response_delay']:
                        time.sleep(task['response_delay'])
                    try:
                        return self.send(dict(receipt=receipt))
                    except (BrokenPipeError, ConnectionResetError):
                        owner.event('effect-response-lost', token=token)
                        return
                if not self.path.endswith('/chat/completions'):
                    return self.send(dict(error='unknown-fixture-endpoint'), 404)
                messages = body.get('messages', [])
                user_indexes = [(i, re.search(r'PILOT_[A-Z0-9_]+', str(m.get('content', ''))))
                                for i, m in enumerate(messages) if m.get('role') == 'user']
                marked = [(i, match.group()) for i, match in user_indexes if match]
                if not marked:
                    return self.send(dict(error='missing-task-marker'), 400)
                index, token = marked[-1]
                task = owner.tasks.get(token)
                if not task:
                    return self.send(dict(error='unknown-task-marker'), 400)
                results = [m for m in messages[index+1:] if m.get('role') == 'tool']
                names = [t.get('function', {}).get('name') for t in body.get('tools', [])]
                owner.event('provider-request', token=token, tool_results=len(results), request_bytes=size,
                            model=body.get('model'), path=self.path)
                if results:
                    text = json.dumps(results, ensure_ascii=False)
                    content = ('ACCEPTED:' if 'RECEIPT:'+token in text else 'CONTROLLED_ERROR:')+token
                    message = dict(role='assistant', content=content)
                    owner.event('provider-tool-result', token=token, receipt_seen='RECEIPT:'+token in text,
                                error_seen=bool(re.search(r'error|failed|not found|unavailable', text, re.I)),
                                result_sha256=hashlib.sha256(text.encode()).hexdigest())
                    finish = 'stop'
                else:
                    tool = task['tool']
                    arguments = dict(token=token, action=task['action'])
                    if tool not in names and 'tool_call' in names:
                        arguments = dict(id=tool, args=arguments)
                        tool = 'tool_call'
                    call = dict(id='call_'+hashlib.sha256(token.encode()).hexdigest()[:24], type='function',
                                function=dict(name=tool, arguments=json.dumps(arguments)))
                    message = dict(role='assistant', content=None, tool_calls=[call])
                    finish = 'tool_calls'
                identifier = 'fixture-'+hashlib.sha256(token.encode()).hexdigest()[:24]
                common = dict(id=identifier, created=1760000000, model='fixture-model')
                if not body.get('stream'):
                    return self.send(dict(**common, object='chat.completion', choices=[dict(index=0, message=message, finish_reason=finish)],
                                          usage=dict(prompt_tokens=0, completion_tokens=0, total_tokens=0)))
                delta = dict(message)
                if 'tool_calls' in delta:
                    delta['tool_calls'] = [dict(index=i, **c) for i, c in enumerate(delta['tool_calls'])]
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                try:
                    for value, reason in [(delta, None), ({}, finish)]:
                        frame = dict(**common, object='chat.completion.chunk', choices=[dict(index=0, delta=value, finish_reason=reason)])
                        encoded = ('data: '+json.dumps(frame)+'\n\n').encode()
                        owner.transmit_bytes += len(encoded)
                        self.wfile.write(encoded)
                    self.wfile.write(b'data: [DONE]\n\n')
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    owner.event('provider-disconnected', token=token)
        return Handler


def process_snapshot(pid):
    """Live product descendants only; exited short-lived processes may be missed."""
    rows = {}
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            data = path.read_text()
            fields = data[data.rfind(')')+2:].split()
            rows[int(path.parent.name)] = fields
        except (OSError, ValueError):
            continue
    members = {pid} if pid in rows else set()
    while True:
        more = members | {p for p, fields in rows.items() if int(fields[1]) in members}
        if more == members:
            break
        members = more
    values = dict(processes=len(members), threads=0, open_fds=0, rss_bytes=0, pss_bytes=0, swap_bytes=0,
                  cpu_user_seconds=0, cpu_system_seconds=0, read_bytes=0, write_bytes=0, read_chars=0, write_chars=0)
    errors = []
    ticks = os.sysconf('SC_CLK_TCK')
    for member in sorted(members):
        directory = Path('/proc')/str(member)
        try:
            status = directory.joinpath('status').read_text()
            rollup = directory.joinpath('smaps_rollup').read_text()
            for field, name, factor in [('VmRSS', 'rss_bytes', 1024), ('Threads', 'threads', 1), ('VmSwap', 'swap_bytes', 1024)]:
                found = re.search(r'^'+field+r':\s+(\d+)', status, re.M)
                if found:
                    values[name] += int(found[1])*factor
            pss = re.search(r'^Pss:\s+(\d+)', rollup, re.M)
            values['pss_bytes'] += int(pss[1])*1024 if pss else 0
            values['open_fds'] += len(list(directory.joinpath('fd').iterdir()))
            values['cpu_user_seconds'] += int(rows[member][11])/ticks
            values['cpu_system_seconds'] += int(rows[member][12])/ticks
            io = dict(line.split(': ', 1) for line in directory.joinpath('io').read_text().splitlines())
            for field, name in [('read_bytes', 'read_bytes'), ('write_bytes', 'write_bytes'), ('rchar', 'read_chars'), ('wchar', 'write_chars')]:
                values[name] += int(io[field])
        except (OSError, ValueError, KeyError) as error:
            errors.append(dict(pid=member, error=type(error).__name__))
    return dict(**values, pids=sorted(members), partial_reads=errors,
                limitation='Live Gateway descendants. Exited process counters are not accumulated; RSS is a sum, PSS is proportional.')


def cgroup_snapshot():
    root = Path('/measurement/cgroup')
    fields = ['cpu.stat', 'memory.current', 'memory.peak', 'memory.swap.current', 'memory.events',
              'pids.current', 'pids.peak', 'io.stat', 'cpu.pressure', 'memory.pressure', 'io.pressure']
    values = {}
    for name in fields:
        try:
            values[name] = (root/name).read_text().strip()
        except OSError:
            values[name] = None
    return dict(counters=values, scope='Owned run cgroup: product, fixture, controller and tmpfs; not product-only.',
                missing_counter_reason='Kernel/controller counter unavailable' if any(v is None for v in values.values()) else None)


def checkpoint(gateway, root, fixture, name):
    loopback = None
    try:
        line = next(line for line in Path('/proc/net/dev').read_text().splitlines() if line.strip().startswith('lo:'))
        fields = line.split(':', 1)[1].split()
        loopback = dict(receive_bytes=int(fields[0]), transmit_bytes=int(fields[8]))
    except (OSError, StopIteration, ValueError):
        pass
    return dict(phase=name, monotonic_ns=time.monotonic_ns(), product=process_snapshot(gateway.process.pid),
                cgroup=cgroup_snapshot(), state=pilot.allocation(root),
                namespace_loopback=loopback, fixture_http_payload=dict(received=fixture.receive_bytes, sent=fixture.transmit_bytes),
                io_wait_seconds=None, io_wait_reason='Per-process reliable IO-wait attribution is unavailable; retain cgroup IO pressure separately.',
                network_scope='Isolated loopback only; kernel counters include protocol overhead and fixture traffic.')


def wait_events(fixture, kind, tokens, seconds=8):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        seen = {e.get('token') for e in fixture.events if e['kind'] == kind}
        if set(tokens) <= seen:
            return True
        time.sleep(.025)
    return False


def wave(gateway, fixture, tokens, same_session=False, gated=False, observe=None):
    if gated:
        fixture.release.clear()
    barrier = threading.Barrier(len(tokens))
    def request(token):
        barrier.wait(timeout=5)
        return gateway.request(token, session_key='shared-'+tokens[0] if same_session else token)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tokens)) as executor:
        futures = [executor.submit(request, token) for token in tokens]
        try:
            if gated:
                arrived = wait_events(fixture, 'effect-start', tokens)
                if observe:
                    observe(arrived)
        finally:
            fixture.release.set()
        return [future.result(timeout=40) for future in futures]


def selfcheck():
    """Positive/negative fixture controls without starting a product runtime."""
    fixture = MechanismFixture()
    try:
        token = 'PILOT_FIXTURE_SELFTEST'
        fixture.register(token)
        connection = http.client.HTTPConnection('127.0.0.1', 18080, timeout=3)
        for item, expected in [(token, 200), ('PILOT_UNREGISTERED', 400)]:
            connection.request('POST', '/effect', json.dumps(dict(token=item, owner='fixture-selfcheck')), {'Content-Type': 'application/json'})
            response = connection.getresponse()
            data = json.loads(response.read())
            assert response.status == expected
            if expected == 200:
                assert data['receipt'] == 'RECEIPT:'+token
        connection.close()
        assert fixture.receipts == {token: 1}
        return dict(independent_effect_control=True, unregistered_effect_rejected=True, synthetic_provider=True)
    finally:
        fixture.close()


def run_scenario(root, scenario, unit=1):
    """Each independent unit creates a fresh native Gateway and fixture."""
    mode = SCENARIOS[scenario]
    family = scenario.rsplit('-S', 1)[0]
    token = 'PILOT_MECHANISM_'+scenario.replace('-', '_')+'_U'+str(unit)
    fixture = MechanismFixture()
    gateway = None
    requests, phases, assertions, metadata = [], [], [], {}
    observation = dict(scenario_id=scenario, unit=unit, native_invoked=False, fixture_validated=False)
    def check(name, value, evidence=('requests', 'independent-events')):
        assertions.append(dict(name=name, verdict='pass' if value else 'fail', evidence=list(evidence)))
    def register(suffix, **options):
        name = token+'_'+suffix
        fixture.register(name, **options)
        return name
    def capture(name):
        phases.append(checkpoint(gateway, root, fixture, name))
    try:
        gateway = pilot.Gateway(root, configurer=lambda path: configure(path, scenario))
        gateway.ready()
        # Independent positive control ensures load failures are not a broken fixture.
        control = register('CONTROL', tool='eval_control' if family == 'EXT-09' and mode == 'collision' else 'eval_probe')
        positive = gateway.request(control)
        if not positive['accepted'] or fixture.receipts.get(control) != 1:
            raise RuntimeError('Native positive control failed: '+json.dumps(positive)[:1500])
        observation.update(fixture_validated=True, native_invoked=True)
        capture('warm-idle')
        begin = len(fixture.events)
        start = time.monotonic()
        measured = []
        if family == 'EXT-09':
            if mode == 'failure-during-task':
                slow = register('A', delay=.8)
                broken = register('B', tool='eval_other', action='throw', fail=True)
                measured = [slow, broken]
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    future = executor.submit(gateway.request, slow)
                    if not wait_events(fixture, 'effect-start', [slow]):
                        raise RuntimeError('Composition failure intervention did not overlap the healthy task')
                    requests.append(gateway.request(broken))
                    requests.append(future.result(timeout=40))
                check('healthy-task-survives-other-plugin-error', requests[1]['accepted'] and fixture.receipts.get(slow) == 1)
                check('throwing-plugin-does-not-report-completion', not requests[0]['accepted'] and not fixture.receipts.get(broken))
            else:
                measured = [register('A'), register('B', tool='eval_probe' if mode == 'collision' else 'eval_other')]
                requests = [gateway.request(item) for item in measured]
            capture('after-composition')
            effects = [e for e in fixture.events[begin:] if e['kind'] == 'effect-commit']
            if mode == 'collision':
                check('collision-does-not-duplicate-effects', all(fixture.receipts.get(t, 0) <= 1 for t in measured))
                metadata['collision_outcomes'] = [dict(token=t, owners=[e['owner'] for e in effects if e['token'] == t], accepted=r['accepted']) for t, r in zip(measured, requests)]
                metadata['collision_contract'] = 'Record selected owner or explicit refusal. No undocumented owner precedence is assumed.'
            elif mode != 'failure-during-task':
                check('both-plugins-execute', all(r['accepted'] for r in requests) and {e['owner'] for e in effects} == {'composition-a', 'composition-b'})
            if mode == 'config':
                check('plugin-configuration-remains-local', len(effects) == 2 and all(e['config_tag'] == ('CONFIG_A' if e['owner'] == 'composition-a' else 'CONFIG_B') for e in effects))
            if mode == 'dependencies':
                check('private-dependency-versions-remain-local', len(effects) == 2 and all(e['dependency_version'] == ('1.0.0' if e['owner'] == 'composition-a' else '2.0.0') for e in effects))
            metadata.update(core_files_modified=0, private_core_imports=0, plugin_api='registerTool, pluginConfig',
                            dependency_fixture='Tiny versioned local ESM packages; no npm dependency downloads or core imports.')
        elif family == 'COST-01':
            count = {'idle': 0, 'one-session': 1, 'four-sessions': 4, 'sixteen-sessions': 16, 'drained': 16}[mode]
            if count:
                measured = [register('T'+str(i), gate=True) for i in range(count)]
                def active(arrived):
                    time.sleep(.3)
                    capture('active-sessions')
                    metadata['all_sessions_reached_effect'] = arrived
                requests = wave(gateway, fixture, measured, gated=True, observe=active)
                check('declared-active-session-count-reached', metadata['all_sessions_reached_effect'])
            else:
                time.sleep(.5)
                capture('idle-dwell')
            time.sleep(.5)
            capture('post-completion-idle')
            metadata.update(active_session_target=count, payload_policy='Identical tool/receipt payload, fresh independent sessions; positive control remains in warm baseline.')
        elif family == 'COST-06':
            if mode == 'idle':
                time.sleep(.5)
                capture('idle-dwell')
            elif mode == 'cancel-cleanup':
                item = register('CANCEL', gate=True)
                measured = [item]
                fixture.release.clear()
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(gateway.request, item)
                        reached = wait_events(fixture, 'effect-start', [item])
                        capture('before-cancellation')
                        result = hook_cases.rpc(gateway, 'sessions.abort', dict(key='agent:main:pilot:'+item.lower()))
                        fixture.release.set()
                        requests = [future.result(timeout=40)]
                        metadata.update(cancel_rpc=result, cancellation_boundary_reached=reached)
                        check('cancel-command-accepted', result['returncode'] == 0)
                        check('cancellation-boundary-exercised', reached)
                finally:
                    fixture.release.set()
                # An uncooperative external service may still commit. Report it;
                # do not turn its effect into a claimed model/task completion.
                check('no-false-task-completion-after-abort', not requests[0]['accepted'])
                metadata['cancellation_contract'] = 'External fixture can finish after abort; effect survival is observed separately.'
                time.sleep(.7)
                capture('post-cancellation-drain')
            else:
                counts = [1, 4, 8] if mode == 'concurrency-sweep' else [1]
                for count in counts:
                    action = 'cpu' if mode == 'cpu-pressure' else 'io' if mode == 'io-network' else 'effect'
                    items = [register(f'C{count}T{i}', action=action, delay=.1) for i in range(count)]
                    measured.extend(items)
                    requests.extend(wave(gateway, fixture, items))
                    capture('completed-wave-'+str(count))
                if mode == 'cpu-pressure':
                    work = [e for e in fixture.events[begin:] if e['kind'] == 'tool-work' and e.get('cpu_loop_ms', 0) >= 550]
                    check('native-cpu-work-exercised', len(work) == 1)
                    metadata['pressure_condition'] = 'One 600 ms synchronous CPU loop inside the native plugin; 2-core outer cgroup ceiling.'
                if mode == 'io-network':
                    work = [e for e in fixture.events[begin:] if e['kind'] == 'tool-work']
                    check('declared-file-io-exercised', any(e.get('file_write_bytes') == e.get('file_read_bytes') == 262144 for e in work))
                    check('declared-loopback-payload-exercised', any(e.get('http_payload_read_bytes') == 262144 for e in work))
                    metadata['io_condition'] = '256 KiB tmpfs write/read and 256 KiB loopback HTTP read; block-device writes may be zero, not an SSD benchmark.'
            metadata['hardware'] = 'PSS/RSS/swap/CPU/IO/fds/processes at phase boundaries, 200 ms product sampler, owned cgroup and loopback counters.'
        else:
            same = family == 'PERF-06' and mode in {'shared-session', 'long-transaction'}
            delay = 1 if mode in {'slow-service', 'recovery'} else .05
            if mode == 'steady':
                for i in range(8):
                    item = register('T'+str(i), delay=delay)
                    measured.append(item)
                    requests.append(gateway.request(item))
            else:
                measured = [register('T'+str(i), delay=delay, response_delay=.5 if mode == 'delayed-commit' else 0) for i in range(8)]
                if mode == 'long-transaction':
                    # Hold an actual native state database write transaction,
                    # independently of the tool. Connection lives in this thread.
                    candidates = []
                    for database in (root/'state').rglob('*.sqlite'):
                        connection = sqlite3.connect(str(database), timeout=.2)
                        tables = {r[0] for r in connection.execute("select name from sqlite_master where type='table'")}
                        connection.close()
                        if 'transcript_events' in tables:
                            candidates.append(database)
                    if len(candidates) != 1:
                        raise RuntimeError('Cannot identify the native transcript database for the declared write-lock intervention')
                    locked, release = threading.Event(), threading.Event()
                    lock_errors = []
                    def hold_transaction():
                        try:
                            connection = sqlite3.connect(str(candidates[0]), timeout=2)
                            connection.execute('BEGIN IMMEDIATE')
                            fixture.event('state-write-lock-acquired', database=str(candidates[0].relative_to(root)))
                            locked.set()
                            release.wait(timeout=5)
                            connection.rollback()
                            connection.close()
                            fixture.event('state-write-lock-released')
                        except Exception as error:
                            lock_errors.append(type(error).__name__+': '+str(error))
                            locked.set()
                    holder = threading.Thread(target=hold_transaction)
                    holder.start()
                    if not locked.wait(timeout=3) or lock_errors:
                        release.set()
                        holder.join(timeout=6)
                        raise RuntimeError('Native write-lock fixture failed: '+str(lock_errors))
                    timer = threading.Timer(1, release.set)
                    timer.start()
                    try:
                        requests = wave(gateway, fixture, measured, same_session=same)
                    finally:
                        release.set()
                        timer.cancel()
                        holder.join(timeout=6)
                    if lock_errors:
                        raise RuntimeError('Native write-lock fixture failed: '+str(lock_errors))
                    metadata['transaction_condition'] = 'BEGIN IMMEDIATE on the native transcript SQLite database, rollback after 1 second; no schema or rows modified.'
                else:
                    requests = wave(gateway, fixture, measured, same_session=same)
                if mode == 'recovery':
                    recovery = [register('RECOVER'+str(i), delay=.05) for i in range(4)]
                    requests.extend(wave(gateway, fixture, recovery))
                    measured.extend(recovery)
                    metadata['recovery_task_count'] = len(recovery)
            capture('load-drained')
            metadata.update(same_session=same, task_count=len(measured), tool_service_delay_ms=delay*1000,
                            native_max_concurrent=gateway.config['agents']['defaults']['maxConcurrent'],
                            load_condition='8 simultaneous requests; PERF-05 uses 2 native active slots, PERF-06 uses 16. Recovery adds 4 short requests; closed finite queueing load.')
        elapsed = time.monotonic()-start
        events = fixture.events[begin:]
        valid_completion = [t for t in measured if fixture.receipts.get(t) == 1]
        if family != 'EXT-09' and mode != 'cancel-cleanup':
            check('all-task-responses-complete', all(r['accepted'] for r in requests))
            check('exactly-one-effect-per-task', len(valid_completion) == len(measured))
        check('no-duplicate-effects', all(fixture.receipts.get(t, 0) <= 1 for t in measured))
        check('no-fixture-gate-timeouts', not any(e['kind'] == 'fixture-gate-timeout' for e in events))
        native = pilot.native_evidence(root, measured)
        capture('before-stop')
        resources = gateway.sampler.summary()
        gateway.stop()
        capture('stopped')
        metadata['stop_exit_code'] = gateway.process.returncode
        metadata['gateway_pid_removed'] = not Path('/proc', str(gateway.process.pid)).exists()
        check('owned-gateway-stopped', metadata['gateway_pid_removed'], ('phase-checkpoints',))
        compact = lambda r: {k: v for k, v in r.items() if k != 'response_excerpt'}
        observation.update(state='pass' if all(a['verdict'] == 'pass' for a in assertions) else 'fail',
            assertions=assertions, requests=[compact(r) for r in requests], positive_control=compact(positive),
            events=events, phases=phases, metadata=metadata, resources=resources,
            measured_task_count=len(measured), completed_effect_count=len(valid_completion),
            elapsed_seconds=elapsed, goodput_per_second=sum(r['accepted'] for r in requests)/elapsed,
            peak_actual_effect_overlap=pilot.peak_overlap(events),
            native_records=dict(tokens=native['tokens'], native_log_sha256=native['native_log_sha256'], native_log_bytes=native['native_log_bytes']),
            config_sha256=hashlib.sha256((root/'config.json').read_bytes()).hexdigest(),
            source_plugin_sha256={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('composition-*/index.js')},
            paid_model_calls=0, usage_note='Scripted local provider; synthetic zero usage is not actual token cost or a model ability score.')
    except Exception as error:
        observation.update(state='harness-error', reason=type(error).__name__+': '+str(error)[:3000])
    finally:
        fixture.release.set()
        if gateway:
            gateway.stop()
        fixture.close()
        shutil.rmtree(root, ignore_errors=True)
        observation['owned_state_retained'] = root.exists()
    return observation
