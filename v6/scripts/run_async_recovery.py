"""R06/R07 native acknowledged background work; HTTP transport contrast is separate.

OpenClaw uses authenticated operator chat.send, retaining its native recovery
authority; Hermes uses native /v1/runs. No simulated product scheduler or
evaluator-driven automatic replay is credited to either product.
"""
import json, os, time, uuid
from runtime import R, OLD, configuration, save
from controlled import Plan, shell
from gateway import Gateway
from run_recovery import stop_owner
from run_approvals import oc_cli
from run_state_ops import db_inventory


def find_run(value):
    if isinstance(value, dict):
        if value.get('runId') or value.get('run_id'):
            return value.get('runId') or value.get('run_id')
        for child in value.values():
            got = find_run(child)
            if got:
                return got
    if isinstance(value, list):
        for child in value:
            got = find_run(child)
            if got:
                return got
    return None


def one(kind, unit, family):
    run = R / 'runs-native-async-recovery' / kind / f'u{unit}' / family
    if (run / 'result.json').exists():
        return json.loads((run / 'result.json').read_text())
    if run.exists():
        raise RuntimeError('Preserve partial native background recovery: ' + str(run))
    run.mkdir(parents=True)
    configuration(family, run / 'state')
    work = run / 'workspace'
    work.mkdir()
    token = f'NATIVE_ASYNC_TASK_{kind}_{unit}_{family}'
    (work / 'PROMPT.md').write_text('Controlled native background recovery ' + token)
    (work / 'slow.py').write_text("import os,time,json\nfrom pathlib import Path\n"
        "Path('/workspace/STARTED.json').write_text(json.dumps({'pid':os.getpid(),'pid_namespace':os.readlink('/proc/self/ns/pid')}))\n"
        "time.sleep(8)\nwith Path('/workspace/effects.jsonl').open('a') as f:f.write('COMMIT\\n')\nprint('COMMITTED')\n")
    (work / 'finish.py').write_text("from pathlib import Path\np=Path('/workspace/effects.jsonl')\n"
        "rows=p.read_text().splitlines() if p.exists() else []\n"
        "if not rows:\n with p.open('a') as f:f.write('COMMIT\\n')\n"
        "Path('/workspace/FINISHED').write_text('receipt reconciled')\nprint('FINISHED')\n")
    fixture = Plan(run, family, [shell('python3 /workspace/slow.py'), shell('python3 /workspace/finish.py')])
    gateway = Gateway(run, family, fixture, persistent_namespace=(kind == 'R07'))
    logical = f'native-async-{kind.lower()}-u{unit}'
    session = 'agent:main:main' if family == 'openclaw' else logical
    run_id = None
    responses = []

    def submit(message, label):
        if family == 'openclaw':
            data = oc_cli(gateway, ['gateway', 'call', 'chat.send', '--params', json.dumps({
                'sessionKey': session, 'message': message, 'idempotencyKey': uuid.uuid4().hex,
                'deliver': False}), '--json'], label)
            return dict(status='native_operator_rpc_ack', response=data, run_id=find_run(data))
        status, headers, body = gateway.raw('POST', '/v1/runs', {
            'input': message, 'model': 'deepseek-flash'}, headers={'X-Hermes-Session-Key': session})
        try:
            data = json.loads(body)
        except ValueError:
            data = {'raw': body.decode(errors='replace')}
        return dict(status=status, response=data, run_id=find_run(data))

    def ledger():
        path = work / 'effects.jsonl'
        return path.read_text().splitlines() if path.exists() else []

    print('NATIVE_ASYNC_RECOVERY_START', kind, unit, family, flush=True)
    try:
        gateway.start()
        initial = submit('Run the authorized controlled background work ' + token, 'native-background-admit')
        save(run / 'native-admission.json', initial)
        run_id = initial['run_id']
        if not run_id or (family == 'hermes' and initial['status'] != 202):
            raise RuntimeError('Native acknowledged background task admission not established')
        until = time.monotonic() + 35
        while not (work / 'STARTED.json').exists() and time.monotonic() < until:
            time.sleep(.05)
        if not (work / 'STARTED.json').exists():
            raise RuntimeError('Native async positive control did not start the actual tool')
        started = json.loads((work / 'STARTED.json').read_text())
        inventory = db_inventory(run / 'state', token)
        save(run / 'native-admission-state-inventory.json', inventory)
        if not any(row.get('token_hits') for row in inventory):
            raise RuntimeError('No native persisted admission/transcript proof before fault')
        if kind != 'positive' and ledger():
            raise RuntimeError('Fault trigger arrived after commit; retain as invalid timing preflight')
        if kind == 'R07':
            stop_owner(gateway)
            gateway.restart_owner()
            begin = gateway.ready
        else:
            begin = time.monotonic()
        # submit() has returned and its native RPC/HTTP client has closed; no
        # foreground response or evaluator worker is sustaining the admitted task.
        until = begin + 30
        while not (work / 'FINISHED').exists() and time.monotonic() < until:
            time.sleep(.1)
        automatic = (work / 'FINISHED').exists() and ledger() == ['COMMIT']
        rec = dict(kind=kind, unit=unit, family=family, native_run_id=run_id,
                   native_session=session, acknowledged_submission=initial,
                   native_persisted_before_fault=True, tool_identity=started,
                   submitting_client_closed=True, automatic_window_seconds=time.monotonic()-begin,
                   automatically_finished=automatic, effects_before_intervention=ledger(),
                   interventions=[], native_status_observations=[], real_model=False, paid_calls=0)
        if family == 'hermes':
            status, _, raw = gateway.raw('GET', '/v1/runs/' + run_id, timeout=10)
            state = json.loads(raw)
            rec['native_status_observations'].append(dict(status=status, body=state))
            if kind == 'R07' and not automatic and state.get('status') == 'unknown':
                # Acknowledge only after independent synthetic application receipt
                # and exact old-tool PID exit verification; this is an OPERATOR step.
                checked = gateway.harness('POST', '/exec', {'command': ['python3', '-c',
                    "import json;from pathlib import Path;p=Path('/proc/"+str(started['pid'])+"/stat');"
                    "alive=p.exists() and p.read_text().rsplit(')',1)[1].split()[0]!='Z';print(json.dumps({'old_tool_alive':alive}))"]})
                save(run / 'operator-old-tool-exit-verification.json', checked)
                verification = json.loads(checked.get('stdout', '{}'))
                rec['operator_receipt_before_confirmation'] = ledger()
                if verification.get('old_tool_alive') is not False:
                    raise RuntimeError('Do not resolve unknown while old execution might still complete')
                payload = {key: state.get(key) for key in ['admission_id', 'execution_generation']}
                code, _, raw = gateway.raw('POST', '/v1/runs/' + run_id + '/resolve-unknown', payload)
                resolution = dict(status=code, body=json.loads(raw), request=payload)
                rec['interventions'].append(dict(kind='operator_verified_unknown_resolution', native=resolution))
                if code != 200:
                    raise RuntimeError('Native unknown-resolution contract not accepted; inspect before grading')
        if not automatic:
            continuation = submit('Resume the original authorized task. Query its persisted receipt first; finish remaining work only if needed and do not duplicate commits.', 'native-explicit-resume')
            rec['interventions'].append(dict(kind='one_explicit_resume_submission', native=continuation))
            until = time.monotonic() + 30
            while not (work / 'FINISHED').exists() and time.monotonic() < until:
                time.sleep(.1)
        rec.update(effect_count=len(ledger()), finished_after_intervention=(work / 'FINISHED').exists() and ledger() == ['COMMIT'],
                   service_healthy=gateway.owner_alive(),
                   classification='automatic_resume' if automatic else 'confirmation_then_resume' if len(rec['interventions'])>1 else 'one_resume' if (work / 'FINISHED').exists() else 'not_completed',
                   scope='Native acknowledged background task entries and persisted authority. Application receipt reconciliation is explicit; operator unknown resolution is never counted as automatic recovery. No generic exactly-once guarantee is claimed. HTTP Chat Completions disconnect behavior remains a separate entry-lifetime contrast.')
        save(run / 'result.json', rec)
        print('NATIVE_ASYNC_RECOVERY_DONE', kind, unit, family, rec['classification'], rec['effect_count'], flush=True)
        if kind == 'positive' and not automatic:
            raise RuntimeError('Unfaulted native background execution did not complete; fix entry before expanding')
        return rec
    finally:
        gateway.stop()
        fixture.close()


def main():
    os.chdir(OLD)
    for family in ['openclaw', 'hermes']:
        one('positive', 0, family)
    results = []
    for unit in range(1, 4):
        for kind in ['R06', 'R07']:
            for family in (['openclaw', 'hermes'] if unit % 2 else ['hermes', 'openclaw']):
                results.append(one(kind, unit, family))
                save(R / 'results/native-async-recovery.json', results)
    print('NATIVE_ASYNC_RECOVERY_COMPLETE', len(results), flush=True)


if __name__ == '__main__':
    main()
