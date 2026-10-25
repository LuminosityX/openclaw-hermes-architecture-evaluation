"""Configured concurrency, explicit backpressure and a bounded sustained delivery run.

Native whole Gateways execute real tools against fixed protocol responses.
This is a local capacity contract test, not a production-duration soak test.
"""
import concurrent.futures, io, json, os, re, threading, time
from pathlib import Path
from runtime import R, OLD, configuration, save
from controlled import Plan
from gateway import Gateway


def router(names, body):
    messages = body.get('messages', [])
    user = max((i for i, m in enumerate(messages) if m.get('role') == 'user'), default=0)
    match = re.search(r'CAPACITY_[A-Za-z0-9_]+', str(messages[user].get('content', '')))
    if not match:
        raise RuntimeError('Capacity task token missing')
    token = match.group()
    if any(m.get('role') == 'tool' for m in messages[user + 1:]):
        return dict(calls=[], text='DELIVERED ' + token)
    name = next((n for n in names if n in ['exec', 'terminal']), None)
    if not name:
        raise RuntimeError('Native shell tool missing from positive control')
    args = dict(command='python3 /workspace/stamp.py ' + token, background=False)
    if name == 'exec':
        args.update(awaitResults=True, yieldMs=10000)
    return [(name, args)]


class GatedPlan(Plan):
    def __init__(self, *args, **kwargs):
        self.active = self.peak = 0
        self.gated = False
        self.gate = threading.Event()
        self.measure_lock = threading.Lock()
        self.intervals = []
        super().__init__(*args, **kwargs)

    def handler(self):
        Base = super().handler()
        owner = self

        class H(Base):
            def do_POST(self):
                payload = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                body = json.loads(payload)
                self.rfile = io.BytesIO(payload)
                main = bool(body.get('tools'))
                if main:
                    begin = time.monotonic_ns()
                    with owner.measure_lock:
                        owner.active += 1
                        owner.peak = max(owner.peak, owner.active)
                    if owner.gated:
                        owner.gate.wait(timeout=15)
                    time.sleep(.1)
                try:
                    return super().do_POST()
                finally:
                    if main:
                        with owner.measure_lock:
                            owner.active -= 1
                            owner.intervals.append(dict(begin_ns=begin, end_ns=time.monotonic_ns()))
                            save(owner.run / 'provider-intervals.json', owner.intervals)

        return H


def one(unit, family):
    run = R / 'runs-capacity-guards' / f'u{unit}' / family
    if (run / 'result.json').exists():
        return json.loads((run / 'result.json').read_text())
    if run.exists():
        raise RuntimeError('Retain partial capacity probe: ' + str(run))
    run.mkdir(parents=True)
    configuration(family, run / 'state')
    work = run / 'workspace'
    work.mkdir()
    (work / 'PROMPT.md').write_text('Controlled capacity and backpressure fixture.')
    (work / 'stamp.py').write_text(
        "from pathlib import Path\nimport sys\n"
        "with (Path('/workspace')/(sys.argv[1]+'.effects')).open('a') as f:f.write('COMMIT\\n')\n"
        "print(sys.argv[1])\n"
    )
    fixture = GatedPlan(run, family, router=router)
    gateway = Gateway(run, family, fixture, concurrency=2)

    def task(tag):
        token = f'CAPACITY_U{unit}_{tag}'
        result = gateway.chat('Deliver the controlled task ' + token, token, timeout=55)
        path = work / (token + '.effects')
        effects = path.read_text().splitlines() if path.exists() else []
        return dict(token=token, status=result['status'], response=result,
                    effects=effects, correct=result['status'] == 200 and effects == ['COMMIT']
                    and 'DELIVERED ' + token in json.dumps(result['response']))

    print('CAPACITY_GUARDS_START', unit, family, flush=True)
    try:
        gateway.start()
        positive = task('warmup')
        if not positive['correct']:
            save(run / 'positive-control.json', positive)
            raise RuntimeError('Native complete-task capacity positive control failed')
        fixture.gated = True
        fixture.peak = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            pending = [pool.submit(task, f'burst_{i}') for i in range(4)]
            until = time.monotonic() + 5
            while fixture.active < 2 and time.monotonic() < until:
                time.sleep(.05)
            time.sleep(.5)
            held_active = fixture.active
            fixture.gate.set()
            burst = [f.result() for f in pending]
        fixture.gated = False
        burst_peak = fixture.peak
        rejected = [x for x in burst if x['status'] == 429]
        retried = [task(x['token'].split(f'CAPACITY_U{unit}_', 1)[1]) for x in rejected]
        # The same total work and concurrency on each product, with no paid inference.
        began = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            sustained = list(pool.map(lambda i: task(f'sustained_{i}'), range(20)))
        seconds = time.monotonic() - began
        accepted = [x for x in burst if x['status'] == 200]
        backpressure = (held_active > 0 and burst_peak <= 2 and
                        all(x['correct'] for x in accepted) and
                        all(x['status'] in (200, 429) for x in burst) and
                        all(not x['effects'] for x in rejected) and
                        all(x['correct'] for x in retried) and len(accepted) + len(rejected) == 4)
        record = dict(unit=unit, family=family, configured_active_run_cap=2,
                      actual_provider_peak=burst_peak, provider_active_while_held=held_active,
                      burst=burst, explicit_429_count=len(rejected), retries_after_capacity_freed=retried,
                      backpressure_held=backpressure, native_concurrency_limit_held=burst_peak <= 2,
                      sustained_deliveries=sustained, sustained_seconds=seconds,
                      sustained_passed=all(x['correct'] for x in sustained), real_model=False, paid_calls=0,
                      scope='Whole native Gateway, cap 2 and four competing runs; bounded 20-task sustained workload. Explicit rejection and correct queuing both satisfy backpressure. No claim of a multi-hour production soak or a Gateway process RAM cap.')
        save(run / 'result.json', record)
        print('CAPACITY_GUARDS_DONE', unit, family, backpressure, record['sustained_passed'], flush=True)
        return record
    finally:
        fixture.gate.set()
        gateway.stop()
        fixture.close()


def main():
    os.chdir(OLD)
    results = []
    for unit in range(1, 4):
        for family in (['openclaw', 'hermes'] if unit % 2 else ['hermes', 'openclaw']):
            results.append(one(unit, family))
            save(R / 'results/capacity-guards.json', results)
    print('CAPACITY_GUARDS_COMPLETE', len(results), flush=True)


if __name__ == '__main__':
    main()
