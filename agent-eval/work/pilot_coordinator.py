"""Coordinator only. Subject processes receive public workspaces and clean state."""
import argparse
import csv
import datetime as dt
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from audit_relay import Relay, append, balance, utc

ROOT = Path('/root/Downloads/1023magnitude/agent_eval_handoff')
PROJECT = Path('/root/Documents/Codex/2026-10-24/agent-root-downloads-1023magnitude-agent-eval')
RUNTIME = PROJECT / 'work/subject-runtime'
KEY = PROJECT / 'work/runtime-secrets/deepseek.json'
ENTRY = PROJECT / 'work/namespace_entry.py'
CODEX_SERVER_LIFECYCLE = False
DUMMY = 'sk-evaluation-local-relay-credential-not-a-real-secret'
SPEC = importlib.util.spec_from_file_location('prepare', ROOT / 'tools/prepare_run.py')
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)

def save(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)

def configuration(family, state):
    if family == 'openclaw':
        (state / 'openclaw').mkdir(exist_ok=True)
        cfg = {'models': {'providers': {'deepseek': {
            'baseUrl': 'http://127.0.0.1:18080/ds', 'apiKey': '${DEEPSEEK_API_KEY}',
            'api': 'openai-completions', 'models': [{'id': 'deepseek-flash', 'name': 'DeepSeek Flash',
                'reasoning': True, 'input': ['text'], 'contextWindow': 1000000, 'maxTokens': 384000,
                'compat': {'thinkingFormat': 'deepseek', 'supportsDeveloperRole': False, 'maxTokensField': 'max_tokens'}}]}}},
            'agents': {'defaults': {'workspace': '/workspace', 'model': {'primary': 'deepseek/deepseek-flash', 'fallbacks': []},
                'subagents': {'model': 'deepseek/deepseek-flash'}, 'thinkingDefault': 'high',
                'models': {'deepseek/deepseek-flash': {'params': {'thinking': 'high'}}}}}}
        save(state / 'openclaw.json', cfg)
    elif family == 'hermes':
        cfg = {'model': {'default': 'deepseek-flash', 'provider': 'deepseek', 'base_url': 'http://127.0.0.1:18080/ds/v1'},
               'agent': {'reasoning_effort': 'high', 'run_budget_seconds': 1800},
               'terminal': {'backend': 'local', 'cwd': '/workspace'}, 'fallback_providers': [],
               'delegation': {'provider': 'deepseek', 'model': 'deepseek-flash', 'base_url': 'http://127.0.0.1:18080/ds/v1', 'fallback_providers': []},
               'auxiliary': {}}
        for slot in ['vision', 'compression', 'title_generation', 'session_search', 'curator', 'background_review', 'approval', 'skills_hub', 'mcp', 'web_extract']:
            cfg['auxiliary'][slot] = {'provider': 'deepseek', 'model': 'deepseek-flash', 'base_url': 'http://127.0.0.1:18080/ds/v1',
                                      'reasoning_effort': 'high', 'fallback_chain': [], 'extra_body': {'thinking': {'type': 'enabled'}}}
        home = state / 'hermes'
        home.mkdir(exist_ok=True)
        original_installs = RUNTIME / 'installer-state/hermes/installs'
        if not (home / 'installs').exists():
            subprocess.run(['cp', '-a', '--reflink=auto', str(original_installs), str(home / 'installs')], check=True)
            for metadata in (home / 'installs').rglob('facts.json'):
                metadata.write_text(metadata.read_text().replace('/runtime/installer-state/hermes/installs/', '/state/hermes/installs/'))
        # JSON is valid YAML, avoiding a coordinator dependency on the subject's parser.
        save(home / 'config.yaml', cfg)
    elif family == 'dsh':
        home = state / 'dsh'
        home.mkdir(exist_ok=True)
        patch = '''- id: agent-default-model
  config:
    provider: deepseek-official
    model: deepseek-flash
    reasoningEffort: high
- id: llm-deepseek
  config:
    baseURL: http://127.0.0.1:18080/ds/anthropic
    apiKeyEnv: DEEPSEEK_API_KEY
    thinking: enabled
    reasoningEffort: high
- id: session-title-llm
  config:
    targetWords: 5
    targetCjkCharacters: 10
    maxInputBytes: 4096
    maxOutputTokens: 4096
    timeoutMs: 60000
    provider: deepseek-official
    model: deepseek-flash
'''
        (home / 'cordis.patch.yml').write_text(patch)
    else:
        (state / 'codex').mkdir(exist_ok=True)

def sandbox(state, workspace, relay_dir=None, family=None, command=None, evaluator=None):
    args = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
            '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib',
            '--symlink', 'usr/lib64', '/lib64', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--tmpfs', '/root',
            '--ro-bind', str(RUNTIME), '/runtime', '--bind', str(state), '/state', '--bind', str(workspace), '/workspace',
            '--chdir', '/workspace', '--ro-bind', str(ENTRY), '/bootstrap/namespace_entry.py',
            '--setenv', 'PATH', '/runtime/node-v24.22.1-linux-x64/bin:/usr/local/bin:/usr/bin:/bin',
            '--setenv', 'OPENCLAW_STATE_DIR', '/state/openclaw', '--setenv', 'OPENCLAW_CONFIG_PATH', '/state/openclaw.json',
            '--setenv', 'HERMES_HOME', '/state/hermes', '--setenv', 'HERMES_RUNTIME_DIR', '/runtime/hermes-tools',
            '--setenv', 'DSH_HOME', '/state/dsh', '--setenv', 'DEEPSEEK_API_KEY', DUMMY,
            '--setenv', 'DEEPSEEK_BASE_URL', 'http://127.0.0.1:18080/ds/v1']
    for path in ['/etc/alternatives', '/etc/ssl/certs', '/etc/passwd', '/etc/group', '/etc/localtime']:
        if Path(path).exists():
            args += ['--ro-bind', path, path]
    if relay_dir:
        args += ['--ro-bind', str(relay_dir), '/relay']
    for script_name in ['dsh_web_lifecycle.mjs', 'native_lifecycle.py', 'codex_server_lifecycle.mjs']:
        script = PROJECT/'work'/script_name
        if script.exists():
            args += ['--ro-bind', str(script), '/bootstrap/'+script_name]
    for candidate in workspace.rglob('*'):
        if candidate.is_file() and (candidate.name in ['PROMPT.md', 'RUN_ID.txt', 'test_public.py', 'input.csv', 'long_job.py'] or 'sources' in candidate.relative_to(workspace).parts):
            args += ['--ro-bind', str(candidate), '/workspace/' + str(candidate.relative_to(workspace))]
    if family == 'codex':
        args += ['--bind', str(state / 'codex'), '/root/.codex', '--ro-bind', '/root/.codex/auth.json', '/root/.codex/auth.json']
    if evaluator:
        args += ['--ro-bind', str(evaluator), '/private']
        return args + ['--', 'python3', '/private/check.py', '/workspace']
    return args + ['--', 'python3', '/bootstrap/namespace_entry.py', *(command or ['--check'])]

def product_command(family, task=None):
    if task == 'W6':
        if family=='codex' and CODEX_SERVER_LIFECYCLE:
            return ['node','/bootstrap/codex_server_lifecycle.mjs']
        return ['node','/bootstrap/dsh_web_lifecycle.mjs'] if family=='dsh' else ['python3','/bootstrap/native_lifecycle.py',family]
    if family == 'openclaw':
        return ['node', '/runtime/openclaw/node_modules/openclaw/openclaw.mjs', 'agent', 'exec',
                '--config', '/state/openclaw.json', '--model', 'deepseek/deepseek-flash',
                '--thinking', 'high', '--timeout', '1800', '--cwd', '/workspace', '--state-dir', '/state/openclaw',
                '--message-file', '/workspace/PROMPT.md', '--json']
    if family == 'hermes':
        activation = 'task_activation="$(/runtime/hermes-tools/python-3.14.9+20261021-linux-x64/bin/python3 -m pm.environments --format sh)" || exit; eval "$task_activation"; exec python /runtime/hermes-source/hermes --usage-file /state/usage.json chat --provider deepseek --model deepseek-flash --reasoning high --query-file /workspace/PROMPT.md --format stream-json --in /workspace'
        # Environment composition reads the source checkout's PM state; the subject then works only in /workspace.
        return ['bash', '-c', 'cd /runtime/hermes-source; ' + activation]
    if family == 'dsh':
        return ['bash', '-c', 'exec node /runtime/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js --profile headless --json - < /workspace/PROMPT.md']
    return ['codex', '--no-daemon', '-a', 'never', 'exec', '--ignore-user-config', '--model', 'gpt-6.1-sol',
            '-c', 'model_reasoning_effort="medium"', '-c', 'model_provider="evaluation_gateway"',
            '-c', 'model_providers.evaluation_gateway.name="Evaluation audit relay"',
            '-c', 'model_providers.evaluation_gateway.base_url="http://127.0.0.1:18080/cx/backend-api/codex"',
            '-c', 'model_providers.evaluation_gateway.wire_api="responses"',
            '-c', 'model_providers.evaluation_gateway.requires_openai_auth=true',
            '-c', 'features.apps=false',
            '-c', 'features.enable_request_compression=false', '--json', '--sandbox', 'danger-full-access',
            '--skip-git-repo-check', '-C', '/workspace', '-']

def evaluate(run, record):
    task = record['task']
    workspace = (run / 'workspace').resolve()
    for artifact in workspace.rglob('*'):
        if artifact.is_symlink() and not artifact.resolve().is_relative_to(workspace):
            save(run / 'acceptance.json', {'passed': False, 'error': 'artifact_symlink_escapes_workspace', 'path': str(artifact.relative_to(workspace))})
            return 'failed'
    if task in ['W1', 'W2']:
        result = subprocess.run(sandbox(run / 'runtime-state', run / 'workspace', evaluator=ROOT / 'evaluator_private' / task / 'v1'),
                                capture_output=True, text=True, timeout=30)
        evidence = {'kind': 'isolated_hidden_acceptance', 'task': task, 'passed': result.returncode == 0,
                    'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        save(run / 'acceptance.json', evidence)
        return 'passed' if evidence['passed'] else 'failed'
    result = subprocess.run(['python3', str(ROOT / 'tools/evaluate.py'), '--run', str(run)], capture_output=True, text=True, timeout=30)
    (run / 'evaluation-command.txt').write_text(result.stdout + result.stderr)
    if task == 'W3':
        return 'passed' if result.returncode == 0 else 'failed'
    return 'manual_review_pending'

def update_status(active=None):
    path = ROOT / 'state/status.json'
    status = json.loads(path.read_text())
    records = []
    for p in (ROOT / 'runs').rglob('run_record.json'):
        candidate = json.loads(p.read_text())
        if candidate.get('phase') == 'pilot':
            records.append(candidate)
    launched = [r for r in records if r.get('start_time_utc')]
    finished = [r for r in launched if r.get('end_time_utc')]
    latest = {}
    for record in records:
        key=(record['family'],record['task'])
        if key not in latest or record.get('attempt',1)>latest[key].get('attempt',1):
            latest[key]=record
    status.update({'updated_at_utc': utc(), 'subject_product_runs': len(launched),
                   'paid_model_calls': sum((r.get('model_calls') or 0) for r in records),
                   'readiness': 'pilot_in_progress' if active else 'pilot_checkpoint',
                   'active_run': active,
                   'account_resources': {**status.get('account_resources', {}), 'deepseek_key_provisioned_to_experiment': True}})
    status['pilot'].update({'started_runs': sum(bool(r.get('start_time_utc')) for r in latest.values()), 'completed_runs': sum(bool(r.get('end_time_utc')) for r in latest.values()),
                            'started_distinct_cases': len({(r['family'],r['task']) for r in launched}),
                            'execution_attempts': len(launched),
                            'failed_runs': sum(r.get('quality_status') == 'failed' or bool(r.get('failures')) for r in latest.values()),
                            'failed_attempts_preserved': sum(r.get('quality_status') == 'failed' or bool(r.get('failures')) for r in finished),
                            'status': 'running' if active else 'checkpoint'})
    save(path, status)

def preflight():
    base = PROJECT / 'work/effective-config-preflight'
    base.mkdir(exist_ok=True)
    results = []
    budget = {'lock': threading.Lock(), 'spent': 0., 'reserved': 0., 'limit': 50.}
    for family in ['openclaw', 'hermes', 'codex', 'dsh']:
        location = base / family
        location.mkdir(exist_ok=True)
        state = location / 'state'
        state.mkdir(exist_ok=True)
        workspace = location / 'public'
        workspace.mkdir(exist_ok=True)
        (workspace / 'PROMPT.md').write_text('Public isolation fixture only. No product model invocation.\n')
        configuration(family, state)
        relay = Relay(location, family, budget)
        checked = subprocess.run(sandbox(state, workspace, relay.socket_dir, family), capture_output=True, text=True, timeout=20)
        if family == 'openclaw':
            command = ['node', '/runtime/openclaw/node_modules/openclaw/openclaw.mjs', 'config', 'validate', '--json']
        elif family == 'dsh':
            command = ['node', '/runtime/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js', '--profile', 'headless', '--dump-config']
        elif family == 'codex':
            command = ['codex', 'login', 'status']
        else:
            command = ['bash', '-c', 'cd /runtime/hermes-source; task_activation="$(/runtime/hermes-tools/python-3.14.9+20261021-linux-x64/bin/python3 -m pm.environments --format sh)" || exit; eval "$task_activation"; exec python /runtime/hermes-source/hermes config check']
        configured = subprocess.run(sandbox(state, workspace, relay.socket_dir, family, command), capture_output=True, text=True, timeout=40)
        relay.close()
        data = {'family': family, 'isolation_exit': checked.returncode, 'isolation_stdout': checked.stdout,
                'isolation_stderr': checked.stderr, 'config_exit': configured.returncode,
                'config_stdout': configured.stdout, 'config_stderr': configured.stderr, 'model_calls': relay.calls}
        results.append(data)
        print(json.dumps({'family': family, 'isolation_exit': checked.returncode, 'config_exit': configured.returncode,
                          'model_calls': relay.calls, 'error_excerpt': configured.stderr[-1000:]}), flush=True)
        save(location / 'result.json', data)
    save(ROOT / ('state/evidence/effective_configuration_preflight-' + str(time.time_ns()) + '.json'), {'at_utc': utc(), 'results': results})
    save(ROOT / 'state/evidence/effective_configuration_preflight.json', {'at_utc': utc(), 'results': results})
    return all(r['isolation_exit'] == r['config_exit'] == r['model_calls'] == 0 for r in results)

def run_case(row, budget, attempt=1):
    family, task = row['family'], row['task']
    runs_root = ROOT / 'runs' if attempt == 1 else ROOT / 'runs/retries' / f'attempt{attempt}'
    run = runs_root / 'pilot' / family / task / 'v1/r1'
    if run.exists():
        raise RuntimeError('Existing original run preserved: ' + str(run))
    run = PREPARE.prepare(family, task, 'v1', 1, 'pilot', runs_root=runs_root)
    run.chmod(0o700)
    state = run / 'runtime-state'
    state.mkdir()
    checklist=run/'workspace/MANUAL_CHECKLIST.md'
    if checklist.exists():
        checklist.rename(run/'coordinator_MANUAL_CHECKLIST.md')
    configuration(family, state)
    save(run / 'public-input-manifest.json', {str(p.relative_to(run / 'workspace')): hashlib.sha256(p.read_bytes()).hexdigest() for p in (run / 'workspace').rglob('*') if p.is_file()})
    relay = Relay(run, family, budget, inference_authorized=True)
    record = json.loads((run / 'run_record.json').read_text())
    record['pilot_case_id'] = record['run_id']
    record['attempt'] = attempt
    if attempt > 1:
        record['run_id'] += f'-attempt{attempt}'
        (run / 'workspace/RUN_ID.txt').write_text(record['run_id']+'\n')
    adapter = json.loads((ROOT / f'records/adapter_{family}.json').read_text())
    record.update({'status': 'running', 'start_time_utc': utc(), 'reasoning_effort': 'medium' if family == 'codex' else 'high',
                   'product_version': adapter['version'],
                   'surface': 'fresh isolated CLI session', 'execution_host': 'current Linux host; new mount/PID/network namespace',
                   'service_tier': 'provider_default; API request field retained', 'evaluator_isolation_verified': True,
                   'human_interventions': [], 'actual_model_evidence': 'api-request-*.json + api-response-*.raw + api-audit.jsonl',
                   'limitations': ['Local auditing relay adds transport overhead; same bridge boundary used for all four configurations.']})
    if task=='W6':
        record['surface']='native Web server / Remote-mux client close-reconnect' if family=='dsh' else 'native Gateway/daemon + terminal CLI client hangup and exact-session resume'
        record['lifecycle_variant']='client_close_only; execution namespace remains alive; no network or host-offline variant mixed in'
        record['limitations'].append('CLI hangup or native Web transport client tested on Linux; physical Windows/iOS continuity belongs to deferred W5. No general multi-turn crash-recovery claim from this command fixture.')
        if family=='codex' and CODEX_SERVER_LIFECYCLE:
            record['surface']='Official app-server JSON-RPC over native Unix socket; separate client close/reconnect'
            record['limitations'].append('Official integration surface; app-server docs identify preview/experimental aspects. Not a substitute for Windows/iOS UI validation. CLI outcome is retained separately.')
    save(run / 'run_record.json', record)
    command = sandbox(state, run / 'workspace', relay.socket_dir, family, product_command(family, task))
    save(run / 'launch.json', {'at_utc': utc(), 'command': command, 'network': 'namespace has loopback only; one Unix socket to path/model-validating real HTTPS relay', 'auth_header_values_recorded': False})
    begin = time.monotonic()
    print(f"START {row['order']}/24 {family} {task}", flush=True)
    try:
        with (run / 'transcript.jsonl').open('w') as stdout, (run / 'stderr.log').open('w') as stderr:
            process = subprocess.Popen(command, stdin=subprocess.PIPE if family == 'codex' and task!='W6' else subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            if family == 'codex' and task!='W6':
                process.stdin.write((run / 'workspace/PROMPT.md').read_bytes())
                process.stdin.close()
            save(run / 'process.json', {'pid': process.pid, 'pgid': process.pid, 'state': 'running', 'started_at_utc': utc()})
            update_status({'run_id': record['run_id'], 'pid': process.pid, 'order': int(row['order'])})
            last = begin
            while process.poll() is None:
                time.sleep(2)
                if time.monotonic() - last > 20:
                    record['model_calls'] = relay.calls
                    save(run / 'run_record.json', record)
                    update_status({'run_id': record['run_id'], 'pid': process.pid, 'order': int(row['order'])})
                    print(f"ACTIVE {family} {task} {round(time.monotonic()-begin)}s calls={relay.calls}", flush=True)
                    last = time.monotonic()
                transport_unknown = any(response.get('transport_failure') for response in relay.responses)
                if time.monotonic() - begin > 1800 or relay.violations or transport_unknown:
                    record['failures'].append({'type': 'uncertain_upstream_execution' if transport_unknown else 'timeout' if not relay.violations else 'fixed_model_or_endpoint_gate', 'detail': relay.violations})
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=12)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    break
            record['exit_code'] = process.returncode
            save(run / 'process.json', {'pid': process.pid, 'pgid': process.pid, 'state': 'exited_namespace_destroyed', 'exit_code': process.returncode, 'ended_at_utc': utc()})
    finally:
        relay.close()
    record.update({'status': 'completed_execution', 'end_time_utc': utc(), 'duration_seconds': round(time.monotonic() - begin, 3),
                   'model_calls': relay.calls, 'actual_model': ('gpt-6.1-sol' if family == 'codex' else 'deepseek-flash') if relay.calls else None})
    record['api_responses'] = relay.responses
    if record.get('exit_code') != 0:
        record['failures'].append({'type': 'product_exit_nonzero', 'exit_code': record.get('exit_code'), 'stderr': 'stderr.log'})
    save(run / 'run_record.json', record)
    try:
        record['quality_status'] = evaluate(run, record) if relay.calls else 'not_evaluated_no_inference'
    except Exception as exc:
        record['quality_status'] = 'evaluator_error'
        record['failures'].append({'type': 'evaluator_error', 'error_type': type(exc).__name__})
    if family != 'codex':
        key = json.loads(KEY.read_text())['DEEPSEEK_API_KEY']
        actual_balance = balance(key)
        save(run / 'balance_after.json', actual_balance)
        now_balance = sum(float(info['total_balance']) for info in actual_balance['balance_infos'] if info['currency'] == 'CNY')
        delta = round(max(0., budget['previous_balance'] - now_balance), 8)
        estimate = sum(response.get('estimated_cost_CNY') or 0. for response in relay.responses)
        record['balance_delta_CNY'] = delta
        record['cost_estimated_CNY'] = estimate
        record['cost_actual'] = delta if delta > 0 or not estimate else None
        record['cost_billing_status'] = 'balance_delta_observed' if delta > 0 else 'no_chargeable_usage' if not estimate else 'positive_token_usage_balance_not_yet_reflected'
        record['cost_currency'] = 'CNY'
        record['cost_source'] = 'official account CNY total_balance before/after; account-wide delta, other concurrent use cannot be excluded'
        budget['previous_balance'] = now_balance
        with budget['lock']:
            budget['spent'] = max(budget['spent'], budget['initial_balance'] - now_balance)
            budget['reserved'] = 0.
    else:
        record['cost_source'] = 'existing ChatGPT subscription; raw response usage retained; currency price not assigned'
    record['artifacts'] = [str(p.relative_to(run)) for p in (run / 'workspace').rglob('*') if p.is_file()]
    save(run / 'run_record.json', record)
    append(ROOT / 'records/costs.jsonl', {'at_utc': utc(), 'run_id': record['run_id'], 'model_calls': relay.calls,
                                        'cost_actual': record.get('cost_actual'), 'cost_currency': record.get('cost_currency'), 'cost_source': record['cost_source']})
    for failure in record['failures']:
        append(ROOT / 'records/failures.jsonl', {'at_utc': utc(), 'run_id': record['run_id'], **failure})
    update_status()
    print(f"DONE {family} {task} exit={record.get('exit_code')} quality={record['quality_status']} calls={relay.calls} cost={record.get('cost_actual')}", flush=True)
    return record

def main():
    global CODEX_SERVER_LIFECYCLE
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--through-order', type=int, default=16)
    parser.add_argument('--retry-order', type=int)
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--automatic-only', action='store_true')
    parser.add_argument('--codex-server-lifecycle', action='store_true')
    args = parser.parse_args()
    CODEX_SERVER_LIFECYCLE = args.codex_server_lifecycle
    if args.preflight:
        raise SystemExit(0 if preflight() else 1)
    authorization = json.loads((ROOT / 'records/authorization.json').read_text())
    assert authorization['authorized_to_run_paid_tests'] and authorization['pilot_budget_amount'] == 50
    proof = json.loads((ROOT / 'state/evidence/effective_configuration_preflight.json').read_text())
    assert all(r['isolation_exit'] == r['config_exit'] == r['model_calls'] == 0 for r in proof['results'])
    key = json.loads(KEY.read_text())['DEEPSEEK_API_KEY']
    initial = balance(key)
    initial_cny = sum(float(info['total_balance']) for info in initial['balance_infos'] if info['currency'] == 'CNY')
    baseline_path = ROOT / 'state/evidence/pilot_balance_start.json'
    if baseline_path.exists():
        saved = json.loads(baseline_path.read_text())['balance']
        baseline_cny = sum(float(info['total_balance']) for info in saved['balance_infos'] if info['currency'] == 'CNY')
    else:
        baseline_cny = initial_cny
        save(baseline_path, {'at_utc': utc(), 'balance': initial, 'authorized_limit_CNY': 50})
    historical_estimate = 0.
    for historical_record in (ROOT/'runs').rglob('run_record.json'):
        historical = json.loads(historical_record.read_text())
        if historical.get('phase')=='pilot':
            historical_estimate += sum(response.get('estimated_cost_CNY') or 0. for response in historical.get('api_responses',[]))
            historical_estimate += sum(response.get('unresolved_cost_reservation_CNY') or 0. for response in historical.get('api_responses',[]))
    budget = {'lock': threading.Lock(), 'spent': max(historical_estimate, baseline_cny-initial_cny), 'reserved': 0., 'limit': min(50., baseline_cny), 'initial_balance': baseline_cny, 'previous_balance': initial_cny}
    for row in csv.DictReader((ROOT / 'pilot_order.csv').open()):
        if args.automatic_only and row['task']=='W5':
            continue
        if args.retry_order is not None and int(row['order']) != args.retry_order:
            continue
        if int(row['order']) > args.through_order:
            break
        existing = ROOT / 'runs/pilot' / row['family'] / row['task'] / 'v1/r1/run_record.json'
        if existing.exists() and args.attempt == 1:
            old = json.loads(existing.read_text())
            if old.get('end_time_utc'):
                continue
            raise RuntimeError('Existing execution needs liveness review before continuation: ' + str(existing))
        result = run_case(row, budget, args.attempt)
        if result['failures']:
            print('STOP checkpoint: inspect preserved failure before further launches.', flush=True)
            break

if __name__ == '__main__':
    main()
