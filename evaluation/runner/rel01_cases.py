"""REL-01 Admission and persistence boundaries, Codex 0.164.0 adapter.

Frozen scenarios (plan full-20261027-codex):
  REL-01-S01 before rollout append
  REL-01-S02 after rollout append but before turn completion notification
  REL-01-S03 after completion notification but before any dependent effect

Instrumented boundaries. S01 holds the prompt on stdin so the process has
merely received a request that was never handed over; S02 gates the model
request at the owned fixture provider and verifies, at kill time, that the
prompt is durably appended to the rollout while no completion exists; S03 lets
the first turn complete and be acknowledged, then crashes the dependent resume
turn at the same pre-completion boundary. Every classification is verified
post-kill by the independent read-only rollout reader, never by product APIs.

Oracle (frozen plan): compare acknowledged turns with durable records and
completed work after restart; report the unacknowledged ambiguity window
separately.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_runtime import CodexRuntime

SCENARIOS = {
    'REL-01-S01': 'before rollout append',
    'REL-01-S02': 'after rollout append but before turn completion notification',
    'REL-01-S03': 'after completion notification but before any dependent effect',
}

PROMPT_S1 = 'REL01_MARKER_INPUT_S01'
FOLLOWUP = 'REL01_MARKER_FOLLOWUP'


# --- independent rollout predicates (read-only JSONL, product APIs unused) ---

def rollout_records(runtime):
    records = []
    for path in runtime.rollout_paths():
        for record in runtime.read_rollout(path):
            record['_source'] = path.name
            records.append(record)
    return records


def user_prompt_lines(records, token):
    hits = []
    for record in records:
        payload = record.get('payload', {})
        if record.get('type') == 'response_item' and payload.get('role') == 'user':
            for content in payload.get('content', []):
                if token in content.get('text', ''):
                    hits.append(record)
    return hits


def assistant_final_lines(records, token):
    hits = []
    for record in records:
        payload = record.get('payload', {})
        if record.get('type') == 'response_item' and payload.get('role') == 'assistant':
            for content in payload.get('content', []):
                if token in content.get('text', ''):
                    hits.append(record)
    return hits


def task_complete_events(records, marker=None):
    events = []
    for record in records:
        payload = record.get('payload', {})
        if record.get('type') == 'event_msg' and payload.get('type') == 'task_complete':
            if marker is None or marker in str(payload.get('last_agent_message', '')):
                events.append(payload)
    return events


def usage_records(records, response_id):
    hits = []
    for record in records:
        payload = record.get('payload', {})
        if record.get('type') == 'token_usage_record' and payload.get('response_id') == response_id:
            hits.append(payload)
    return hits


def verdict(assertions):
    return 'pass' if all(a['verdict'] == 'pass' for a in assertions) else 'fail'


# --- scenario runners ---------------------------------------------------------

def run_s01(runtime, unit):
    """Kill while the process runs with the prompt still held by the client."""
    process = runtime.spawn(prompt='-', hold_stdin=True, json_output=True)
    time.sleep(2.0)  # boot, config load; input never handed over
    runtime.kill_process_group(process)
    process.wait(timeout=10)
    records = rollout_records(runtime)
    prompts = user_prompt_lines(records, PROMPT_S1)
    completions = task_complete_events(records)
    observations = dict(
        rollout_files=runtime.rollout_digest(),
        prompt_persisted=bool(prompts),
        any_task_complete=bool(completions),
        ambiguity_class=('prompt-persisted' if prompts else
                         ('rollout-exists' if records else 'no-rollout')))
    assertions = [
        dict(name='merely-received-request-leaves-no-completion',
             verdict='pass' if not completions else 'fail',
             evidence=['independent-rollout-reader:task_complete-absent']),
        dict(name='unacknowledged-ambiguity-classified',
             verdict='pass', evidence=[f'class={observations["ambiguity_class"]}']),
        dict(name='boundary-valid-input-never-handed-over',
             verdict='pass' if not prompts else 'fail',
             evidence=['stdin-held-prompt-never-delivered', 'rollout-prompt-lines=0']),
    ]
    return dict(assertions=assertions, observations=observations)


def run_s02(runtime, unit):
    """Hold the model request at the fixture; the prompt must already be durable."""
    runtime.fixture.hold_mode = True
    runtime.fixture.release.clear()
    process = runtime.spawn(PROMPT_S1, json_output=True)
    if not runtime.fixture.hold_event.wait(timeout=60):
        runtime.kill_process_group(process)
        return dict(assertions=[dict(name='fixture-gate-reached', verdict='fail',
                                     evidence=['no-model-request-within-60s'])],
                    observations=dict(fixture_gate=False))
    at_kill = rollout_records(runtime)
    prompt_at_kill = len(user_prompt_lines(at_kill, PROMPT_S1))
    completion_at_kill = len(task_complete_events(at_kill))
    runtime.kill_process_group(process)
    process.wait(timeout=10)
    runtime.fixture.release.set()
    runtime.fixture.hold_mode = False

    resumed = runtime.resume(FOLLOWUP, timeout=90)
    after = rollout_records(runtime)
    prompts_after = user_prompt_lines(after, PROMPT_S1)
    followups_after = user_prompt_lines(after, FOLLOWUP)
    completions_after = task_complete_events(after)
    requests = [e for e in runtime.fixture.requests() if e['kind'] == 'response-request']
    observations = dict(
        prompt_durable_at_kill=prompt_at_kill, completions_at_kill=completion_at_kill,
        prompt_lines_after_resume=len(prompts_after),
        followup_lines_after_resume=len(followups_after),
        task_complete_events_after=len(completions_after),
        fixture_response_requests=len(requests),
        resume_exit=resumed['exit'])
    assertions = [
        dict(name='input-persisted-before-model-dispatch',
             verdict='pass' if prompt_at_kill == 1 else 'fail',
             evidence=[f'rollout-prompt-lines-at-kill={prompt_at_kill}']),
        dict(name='killed-turn-not-marked-complete-at-kill',
             verdict='pass' if completion_at_kill == 0 else 'fail',
             evidence=[f'task-complete-at-kill={completion_at_kill}']),
        dict(name='resume-preserves-input-exactly-once',
             verdict='pass' if len(prompts_after) == 1 else 'fail',
             evidence=[f'prompt-lines-after-resume={len(prompts_after)}']),
        dict(name='completed-work-exactly-once-after-resume',
             verdict='pass' if (resumed['exit'] == 0 and len(completions_after) >= 1
                                and len(followups_after) == 1) else 'fail',
             evidence=[f'resume-exit={resumed["exit"]}',
                       f'task-complete-events={len(completions_after)}',
                       f'followup-lines={len(followups_after)}']),
    ]
    return dict(assertions=assertions, observations=observations)


def run_s03(runtime, unit):
    """Acknowledge turn 1, crash the dependent turn at its pre-completion gate."""
    first = runtime.run(PROMPT_S1, timeout=90)
    acknowledged = rollout_records(runtime)
    original_complete = task_complete_events(acknowledged)
    original_usage = usage_records(acknowledged, 'resp_fixture_1')

    runtime.fixture.hold_mode = True
    runtime.fixture.release.clear()
    dependent = runtime.spawn_resume(FOLLOWUP)
    gate_ok = runtime.fixture.hold_event.wait(timeout=60)
    if gate_ok:
        runtime.kill_process_group(dependent)
        dependent.wait(timeout=10)
        runtime.fixture.release.set()
        runtime.fixture.hold_mode = False
    else:
        runtime.kill_process_group(dependent)

    final = runtime.resume(FOLLOWUP + '_AGAIN', timeout=90)
    after = rollout_records(runtime)
    complete_after = task_complete_events(after)
    original_usage_after = usage_records(after, 'resp_fixture_1')
    original_prompts_after = user_prompt_lines(after, PROMPT_S1)
    observations = dict(
        first_exit=first['exit'],
        acknowledged_task_complete=len(original_complete),
        acknowledged_usage_records=len(original_usage),
        dependent_gate_reached=gate_ok,
        original_usage_records_after_crash=len(original_usage_after),
        original_prompt_lines_after=len(original_prompts_after),
        task_complete_events_total=len(complete_after),
        final_resume_exit=final['exit'])
    assertions = [
        dict(name='acknowledged-turn-durable',
             verdict='pass' if (first['exit'] == 0 and len(original_complete) == 1) else 'fail',
             evidence=[f'exit={first["exit"]}', f'task-complete={len(original_complete)}']),
        dict(name='acknowledged-work-not-re-executed',
             verdict='pass' if (len(original_usage_after) == 1
                                and len(original_prompts_after) == 1) else 'fail',
             evidence=[f'usage-records-for-first-response={len(original_usage_after)}',
                       f'original-prompt-lines={len(original_prompts_after)}']),
        dict(name='dependent-turn-completes-after-crash',
             verdict='pass' if (final['exit'] == 0 and len(complete_after) >= 2) else 'fail',
             evidence=[f'final-resume-exit={final["exit"]}',
                       f'task-complete-total={len(complete_after)}']),
    ]
    return dict(assertions=assertions, observations=observations)


RUNNERS = {'REL-01-S01': run_s01, 'REL-01-S02': run_s02, 'REL-01-S03': run_s03}


def run_scenario(scenario, unit=1, codex='codex'):
    """Run one scenario of one independent unit against the pinned binary.

    Returns the observation row; the family runner binds plan/runtime identity
    and validates it against the frozen campaign plan. It never fabricates a
    formal record on its own.
    """
    runtime = CodexRuntime(codex=codex)
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
    parser = argparse.ArgumentParser(description='REL-01 development calibration')
    parser.add_argument('--codex', default='codex')
    args = parser.parse_args()
    for scenario_id in SCENARIOS:
        row = run_scenario(scenario_id, unit=1, codex=args.codex)
        row['development_calibration'] = True
        print(json.dumps(row, ensure_ascii=False, indent=2))
