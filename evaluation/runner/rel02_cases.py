"""REL-02 External effects and lost acknowledgments, Codex 0.164.0 adapter.

Frozen scenarios (plan full-20261027-codex):
  REL-02-S01 effect not committed
  REL-02-S02 effect committed and response lost
  REL-02-S03 process dies before recording the tool result

The scripted fixture model issues a real `exec_command` tool call whose shell
command commits an effect at the owned loopback ledger (with an idempotency
key). S01's service rejects the effect; S02's service commits and then drops
the HTTP response; S03's service commits and holds the response while the
controller kills the whole Codex process group. Ground truth lives only in the
independent ledger; reconciliation compares it with the read-only rollout view.

Oracle (frozen plan): the ledger must show the exact effect count; separate
correct reconciliation, safe uncertainty, incorrect replay and falsely
reported completion.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_runtime import CodexRuntime
from rel01_cases import rollout_records, task_complete_events

SCENARIOS = {
    'REL-02-S01': 'effect not committed',
    'REL-02-S02': 'effect committed and response lost',
    'REL-02-S03': 'process dies before recording the tool result',
}


def effect_command(ledger, token, kind=None):
    payload = {'token': token, 'key': f'key-{token}'}
    if kind:
        payload['kind'] = kind
    return ('curl -s -S -m 120 -X POST http://127.0.0.1:%d/effect '
            "-H 'Content-Type: application/json' -d '%s'"
            % (ledger.port, json.dumps(payload)))


def exec_call(command):
    return {'call': {'name': 'exec_command', 'arguments': {'cmd': command}}}


def function_call_lines(records, token):
    """Rollout function_call items whose arguments mention the effect token."""
    hits = []
    for record in records:
        payload = record.get('payload', {})
        if record.get('type') == 'response_item' and payload.get('type') == 'function_call':
            if token in payload.get('arguments', ''):
                hits.append(payload)
    return hits


def function_call_output_lines(records, call_id):
    hits = []
    for record in records:
        payload = record.get('payload', {})
        if record.get('type') == 'response_item' and payload.get('type') == 'function_call_output':
            if payload.get('call_id') == call_id:
                hits.append(payload)
    return hits


def output_text_bounded(outputs, limit=600):
    """Bounded diagnostic capture of tool outputs (never returned to the model)."""
    texts = []
    for payload in outputs:
        output = payload.get('output')
        if isinstance(output, dict):
            output = output.get('content') or output.get('output') or output
        texts.append(str(output)[:limit])
    return texts


def verdict(assertions):
    return 'pass' if all(a['verdict'] == 'pass' for a in assertions) else 'fail'


def run_s01(runtime, unit):
    """The service rejects the effect; the turn must reconcile honestly."""
    token = f'REL02_S01_U{unit}'
    runtime.fixture.script = [
        exec_call(effect_command(runtime.ledger, token, kind='reject')),
        {'reply': 'REL02_S01_FINAL'},
    ]
    result = runtime.run('Perform the requested effect operation exactly as instructed.',
                         timeout=180)
    records = rollout_records(runtime)
    calls = function_call_lines(records, token)
    outputs = []
    for call in calls:
        outputs.extend(function_call_output_lines(records, call.get('call_id')))
    counts = runtime.ledger.counts(token)
    complete = task_complete_events(records, 'REL02_S01_FINAL')
    observations = dict(exit=result['exit'], ledger=counts,
                        function_calls=len(calls), call_outputs=len(outputs),
                        task_complete=len(complete),
                        tool_output_text=output_text_bounded(outputs))
    assertions = [
        dict(name='rejected-effect-not-committed-anywhere',
             verdict='pass' if counts['committed'] == 0 else 'fail',
             evidence=[f'ledger-committed={counts["committed"]}',
                       f'ledger-rejected={counts["rejected"]}']),
        dict(name='failed-call-recorded-with-its-output',
             verdict='pass' if calls and len(outputs) == len(calls) else 'fail',
             evidence=[f'function-calls={len(calls)}', f'outputs={len(outputs)}']),
        dict(name='turn-completes-after-rejected-effect',
             verdict='pass' if result['exit'] == 0 and complete else 'fail',
             evidence=[f'exit={result["exit"]}', f'task-complete={len(complete)}']),
        dict(name='ledger-and-rollout-reconcile',
             verdict='pass' if counts['raw_attempts'] + counts['rejected'] == len(calls) else 'fail',
             evidence=[f'ledger-attempts={counts["raw_attempts"] + counts["rejected"]}',
                       f'rollout-calls={len(calls)}']),
    ]
    return dict(assertions=assertions, observations=observations)


def run_s02(runtime, unit):
    """The service commits, then drops the HTTP response."""
    token = f'REL02_S02_U{unit}'
    runtime.ledger.drop_after_commit = True
    runtime.fixture.script = [
        exec_call(effect_command(runtime.ledger, token)),
        {'reply': 'REL02_S02_FINAL'},
    ]
    result = runtime.run('Perform the requested effect operation exactly as instructed.',
                         timeout=180)
    runtime.ledger.drop_after_commit = False
    records = rollout_records(runtime)
    calls = function_call_lines(records, token)
    outputs = []
    for call in calls:
        outputs.extend(function_call_output_lines(records, call.get('call_id')))
    counts = runtime.ledger.counts(token)
    complete = task_complete_events(records, 'REL02_S02_FINAL')
    observations = dict(exit=result['exit'], ledger=counts,
                        function_calls=len(calls), call_outputs=len(outputs),
                        task_complete=len(complete),
                        safe_uncertainty_window='effect committed, response lost, '
                                                'tool saw a transport error')
    assertions = [
        dict(name='committed-effect-counted-exactly-once',
             verdict='pass' if counts['committed'] == 1 else 'fail',
             evidence=[f'ledger-committed={counts["committed"]}',
                       f'ledger-raw-attempts={counts["raw_attempts"]}']),
        dict(name='no-automatic-replay-after-lost-response',
             verdict='pass' if counts['raw_attempts'] == 1 else 'fail',
             evidence=[f'ledger-raw-attempts={counts["raw_attempts"]}']),
        dict(name='transport-failure-recorded-not-hidden',
             verdict='pass' if calls and len(outputs) == len(calls) else 'fail',
             evidence=[f'function-calls={len(calls)}', f'outputs={len(outputs)}']),
        dict(name='turn-completes-with-safe-uncertainty',
             verdict='pass' if result['exit'] == 0 and complete else 'fail',
             evidence=[f'exit={result["exit"]}', f'task-complete={len(complete)}']),
    ]
    return dict(assertions=assertions, observations=observations)


def run_s03(runtime, unit):
    """Commit succeeds, the service holds the response; kill Codex mid-wait."""
    token = f'REL02_S03_U{unit}'
    runtime.ledger.hold_seconds = 90.0
    runtime.fixture.script = [
        exec_call(effect_command(runtime.ledger, token)),
        {'reply': 'REL02_S03_FINAL'},
    ]
    process = runtime.spawn('Perform the requested effect operation exactly as instructed.',
                            json_output=True)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if runtime.ledger.counts(token)['committed'] >= 1:
            break
        if process.poll() is not None:
            break
        time.sleep(0.05)
    committed_before_kill = runtime.ledger.counts(token)['committed']
    at_kill = rollout_records(runtime)
    calls_at_kill = function_call_lines(at_kill, token)
    outputs_at_kill = []
    for call in calls_at_kill:
        outputs_at_kill.extend(function_call_output_lines(at_kill, call.get('call_id')))
    runtime.kill_process_group(process)
    process.wait(timeout=10)

    resumed = runtime.resume('Continue and finish the task.', timeout=180)
    runtime.ledger.hold_seconds = 0.0
    after = rollout_records(runtime)
    counts = runtime.ledger.counts(token)
    calls_after = function_call_lines(after, token)
    complete = task_complete_events(after, 'REL02_S03_FINAL')
    observations = dict(committed_before_kill=committed_before_kill,
                        calls_at_kill=len(calls_at_kill), outputs_at_kill=len(outputs_at_kill),
                        resume_exit=resumed['exit'], ledger_after=counts,
                        calls_after=len(calls_after), task_complete=len(complete))
    assertions = [
        dict(name='effect-committed-before-kill',
             verdict='pass' if committed_before_kill == 1 else 'fail',
             evidence=[f'ledger-committed-at-kill={committed_before_kill}']),
        dict(name='tool-result-unrecorded-at-kill',
             verdict='pass' if (calls_at_kill and not outputs_at_kill) else 'fail',
             evidence=[f'calls-at-kill={len(calls_at_kill)}',
                       f'outputs-at-kill={len(outputs_at_kill)}']),
        dict(name='resume-does-not-replay-committed-effect',
             verdict='pass' if counts['committed'] == 1 and counts['raw_attempts'] == 1 else 'fail',
             evidence=[f'ledger-committed={counts["committed"]}',
                       f'ledger-raw-attempts={counts["raw_attempts"]}']),
        dict(name='resumed-turn-completes-exactly-once',
             verdict='pass' if (resumed['exit'] == 0 and len(complete) == 1
                                and len(calls_after) == 1) else 'fail',
             evidence=[f'resume-exit={resumed["exit"]}',
                       f'task-complete={len(complete)}', f'calls-after={len(calls_after)}']),
    ]
    return dict(assertions=assertions, observations=observations)


RUNNERS = {'REL-02-S01': run_s01, 'REL-02-S02': run_s02, 'REL-02-S03': run_s03}


def run_scenario(scenario, unit=1, codex='codex'):
    runtime = CodexRuntime(codex=codex, sandbox='workspace-write')
    try:
        result = RUNNERS[scenario](runtime, unit)
        return dict(
            schema_version=1, product='codex', scenario_id=scenario, unit=unit,
            state=verdict(result['assertions']), native_invoked=True,
            fixture_validated=True, assertions=result['assertions'],
            observations=result['observations'],
            target_version='0.164.0',
            target_commit='6aaac694803004a63c6f393d153c96d22521a6b9')
    finally:
        runtime.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='REL-02 development calibration')
    parser.add_argument('--codex', default='codex')
    args = parser.parse_args()
    for scenario_id in SCENARIOS:
        row = run_scenario(scenario_id, unit=1, codex=args.codex)
        row['development_calibration'] = True
        print(json.dumps(row, ensure_ascii=False, indent=2))
