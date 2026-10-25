import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path('/root/Downloads/1023magnitude/agent_eval_handoff')
WORK = Path('/root/Documents/Codex/2026-10-24/agent-root-downloads-1023magnitude-agent-eval/work')
EVIDENCE = ROOT / 'state/evidence'
EVIDENCE.mkdir(parents=True, exist_ok=True)
NOW = dt.datetime.now(dt.timezone.utc).isoformat()

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def capture(argv, cwd=None, timeout=20):
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return {'argv': argv, 'exit_code': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
    except subprocess.TimeoutExpired:
        return {'argv': argv, 'exit_code': None, 'failure': 'preflight_timeout'}

commands = [
    ['codex', '--version'], ['codex', '--help'], ['codex', 'exec', '--help'],
    ['codex', 'login', 'status'], ['node', '--version'], ['npm', '--version'], ['git', '--version']
]
observations = [capture(c, cwd=WORK.parent) for c in commands]
save(EVIDENCE / 'local_cli_probes.json', {'at_utc': NOW, 'scope': 'version_help_and_login_status_only_no_inference', 'commands': observations})
save(EVIDENCE / 'credential_device_presence.json', {
    'at_utc': NOW,
    'nonempty_variable_presence_only': {k: bool(os.environ.get(k)) for k in ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'OIC_MANIFEST_PATH', 'DISPLAY', 'WAYLAND_DISPLAY', 'SSH_AUTH_SOCK']},
    'secret_values_recorded': False,
    'credential_files_opened': False,
    'managed_environment_status_tool_available': False,
    'network_policy_file_present': Path('/etc/codex/network-policy.json').is_file(),
    'network_policy_readiness': 'unverified; no managed environment status tool or policy snapshot available',
    'desktop_mobile_cloud_access': 'not established by executable or display checks'
})

# This is a no-model mount and PID isolation probe, never a subject result.
probe = WORK / 'isolation_probe'
public = probe / 'public'
public.mkdir(parents=True, exist_ok=True)
(public / 'PUBLIC_CANARY.txt').write_text('public fixture only\n')
(probe / 'COORDINATOR_CANARY.txt').write_text('synthetic isolation canary\n')
shell = '''set -eu
test -r /workspace/PUBLIC_CANARY.txt
test ! -e /root/Downloads/1023magnitude/agent_eval_handoff
test ! -e /root/Documents/Codex
test ! -e /root/.codex
test ! -e /proc/1/root/root/Downloads/1023magnitude/agent_eval_handoff
test ! -e /workspace/COORDINATOR_CANARY.txt
printf 'public_mount_readable=true\ncoordinator_paths_absent=true\n'
id
'''
argv = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
        '--clearenv', '--setenv', 'PATH', '/usr/bin:/bin',
        '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin',
        '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
        '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
        '--ro-bind', str(public), '/workspace', '--chdir', '/workspace',
        '--', '/bin/sh', '-c', shell]
isolation = capture(argv, timeout=10)
save(EVIDENCE / 'isolation_probe.json', {
    'at_utc': NOW, 'scope': 'synthetic_public_mount_probe_no_product_no_model',
    'result': isolation, 'passed': isolation['exit_code'] == 0,
    'inference_network_enabled': False, 'production_evaluator_isolation_verified': False,
    'limitations': ['Product process, auth delivery, tool paths, egress allowlist and remote session paths are not yet tested.',
                   'The coordinator remains root/full-access; never use this chat as a subject.',
                   'Do not mount the handoff root, private materials, coordinator memories or broad user credentials.',
                   'A writable-workspace sandbox alone does not prove read isolation.']
})

sources = {
 'deepseek_pricing': 'https://api-docs.deepseek.com/quick_start/pricing/',
 'deepseek_thinking': 'https://api-docs.deepseek.com/guides/thinking_mode/',
 'openclaw_cli': 'https://docs.openclaw.ai/cli',
 'openclaw_agent': 'https://docs.openclaw.ai/cli/agent',
 'openclaw_gateway': 'https://docs.openclaw.ai/cli/gateway',
 'openclaw_deepseek': 'https://docs.openclaw.ai/providers/deepseek',
 'openclaw_thinking': 'https://docs.openclaw.ai/tools/thinking',
 'hermes_cli': 'https://hermes-agent.nousresearch.com/docs/user-guide/cli',
 'hermes_profiles': 'https://hermes-agent.nousresearch.com/docs/user-guide/profiles',
 'hermes_config': 'https://hermes-agent.nousresearch.com/docs/user-guide/configuration',
 'codex_cli': 'https://learn.chatgpt.com/docs/cli/reference',
 'codex_config': 'https://learn.chatgpt.com/docs/config-file/config-reference',
 'codex_subagents': 'https://learn.chatgpt.com/docs/agent-configuration/subagents',
 'dsh_cli': 'https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/README.md',
 'dsh_cli_reference': 'https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/reference/README.md',
 'dsh_providers': 'https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/providers.md',
 'dsh_web': 'https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/index.md'
}
save(EVIDENCE / 'official_sources.json', {
 'checked_at_utc': NOW, 'method': 'official pages opened using web tool; DSH repository fetched through GitHub connector',
 'sources': sources,
 'deepseek_alias_snapshot': {'requested': 'deepseek-flash', 'documented_version': 'DeepSeek-V4.1-Flash-1017', 'runtime_response_verified': False},
 'documentation_conflicts': [
   'DeepSeek integration tutorials mention older Flash aliases and/or Pro defaults; preserve exact experiment model IDs.',
   'Documentation is a capability statement, not a runtime, account entitlement or performance observation.'
 ]
})

common_blockers = ['pilot_budget_and_subscription_consumption_limit_pending', 'wall_clock_and_concurrency_caps_pending',
                   'desktop_mobile_cloud_surfaces_and_W5_W6_devices_pending', 'effective_main_child_auxiliary_request_configuration_unverified',
                   'product_evaluator_isolation_and_egress_allowlist_unverified', 'cancellation_descendant_process_and_log_export_unverified']

details = {
 'openclaw': {
   'status': 'documented_blocked_no_local_executable', 'version': None, 'surface': 'candidate isolated CLI + Gateway; final cross-device surfaces pending',
   'configuration_strategy': {'main_model': 'deepseek/deepseek-flash (provider-qualified product ref; request model must remain deepseek-flash)',
      'reasoning': 'high with thinking enabled; validate actual wire mapping, not UI label alone',
      'service_tier': 'provider default; record actual; no inherited fast/priority',
      'fallback_policy': 'No alternate model; inspect fallbacks and every configurable child/auxiliary slot before execution'},
   'isolated_profile_or_home': 'Fresh per-run --profile, with OPENCLAW_STATE_DIR/OPENCLAW_CONFIG_PATH scoped inside external process isolation; never reuse daily profile',
   'documented_commands_not_run': ['openclaw --profile <run-id> --version', 'openclaw --profile <run-id> models set deepseek/deepseek-flash', 'openclaw --profile <run-id> agent --help', 'openclaw --profile <run-id> gateway --help'],
   'followup_method': 'Candidate same Gateway/session identity through official agent or UI; exact entry/flags and identity continuity pending installation and device selection',
   'log_usage_export_method': 'Retain raw Gateway/session transcript, effective config, usage and provider billing; exact installed export mechanism pending',
   'configurable_auxiliary_models': 'Inventory per-agent/subagent/default/fallback/auxiliary slots in installed version; pin all configurable generation to deepseek-flash',
   'exceptions': ['Unconfigurable safety or embedding services must be recorded separately; do not disable safety'],
   'required_access': ['DeepSeek API billing account (user confirmed possession)', 'Protected key provisioning (not present in current process)', 'Install/version freeze and selected Gateway/device surfaces'],
   'blockers': ['openclaw_not_found_in_PATH', 'deepseek_key_not_provisioned_to_experiment'] + common_blockers,
   'source_keys': ['openclaw_cli','openclaw_agent','openclaw_gateway','openclaw_deepseek','openclaw_thinking','deepseek_thinking']
 },
 'hermes': {
   'status': 'documented_blocked_no_local_executable', 'version': None, 'surface': 'candidate isolated CLI; Desktop/Gateway/bot continuity surfaces pending',
   'configuration_strategy': {'main_model': 'deepseek-flash through DeepSeek direct endpoint', 'reasoning': 'agent.reasoning_effort high; verify thinking enabled in actual requests',
      'endpoint': 'https://api.deepseek.com', 'service_tier': 'provider default; record actual',
      'fallback_policy': 'Inspect fallback_providers, per-auxiliary fallback_chain, delegation and MoA slots; no alternate model'},
   'isolated_profile_or_home': 'Fresh HERMES_HOME/profile in an external whole-process sandbox; profile isolation alone still shares host CLI state',
   'documented_commands_not_run': ['hermes chat --provider deepseek --model deepseek-flash --query-file /workspace/PROMPT.md', 'hermes chat --help', 'hermes profile --help'],
   'followup_method': 'Official --resume <session_id>; preserve exact run/session identity. Never use latest across cases. Not exercised',
   'log_usage_export_method': 'Per-profile sessions/logs plus raw CLI stdout/stderr and provider usage/billing. Installed export and durable flush unverified',
   'configurable_auxiliary_models': 'Explicitly pin installed auxiliary tasks, compression, delegation and enabled MoA slots to deepseek-flash. Verify fallback and implicit/default routes',
   'exceptions': ['Record unconfigurable safety/embedding separately; retain safety. Auxiliary reasoning defaults may differ and need explicit verification'],
   'required_access': ['DeepSeek API billing account (user confirmed possession)', 'Protected key provisioning (not present in current process)', 'Installed release and approved Desktop/Gateway/bot entry'],
   'blockers': ['hermes_not_found_in_PATH','deepseek_key_not_provisioned_to_experiment'] + common_blockers,
   'source_keys': ['hermes_cli','hermes_profiles','hermes_config','deepseek_thinking']
 },
 'codex': {
   'status': 'local_cli_and_subscription_auth_verified_runtime_model_pending', 'version': 'codex-cli 0.163.0',
   'surface': 'local CLI observed; current coordination chat uses user subscription; tested Desktop/Web/Mobile/Cloud path still pending',
   'configuration_strategy': {'main_model': 'gpt-6.1-sol', 'reasoning': 'model_reasoning_effort = medium',
      'service_tier': 'provider default in clean experiment config; record actual; do not inherit daily fast/priority',
      'fallback_policy': 'No model switches; inspect role-specific agent config and configurable generation/review slots'},
   'isolated_profile_or_home': 'Fresh experiment OS-user/runtime state and clean config, with narrowly delivered subscription auth. exec --ignore-user-config exists; not sufficient alone to isolate memories/skills/plugins or private reads',
   'documented_commands_not_run': ['codex --no-daemon exec --ignore-user-config --model gpt-6.1-sol -c model_reasoning_effort="medium" --json --skip-git-repo-check -C /workspace -', 'codex exec resume <session-id>'],
   'cli_syntax_evidence': 'state/evidence/local_cli_probes.json; version/help/login-status only; candidate model invocation not executed',
   'followup_method': 'CLI exec resume <exact-session-id> exists in help; fresh initial session per case. Cross-device continuation must use a genuinely connected official surface',
   'log_usage_export_method': '--json raw event stream, persisted session identity and exact effective config, separate subscription usage/credits snapshot. Exact actual-model and tier fields still to verify',
   'configurable_auxiliary_models': 'Pin every configurable child role/generation model to gpt-6.1-sol; role TOML and default inheritance must be checked before subject work',
   'exceptions': ['Unconfigurable safety/embedding services unknown until inventory; retain safety and record separately'],
   'required_access': ['User confirmed existing subscription', 'CLI reports Logged in using ChatGPT', 'Subscription pilot consumption cap and connected device surfaces still required'],
   'blockers': common_blockers,
   'source_keys': ['codex_cli','codex_config','codex_subagents']
 },
 'dsh': {
   'status': 'documented_blocked_no_local_executable', 'version': None, 'surface': 'candidate isolated official headless CLI + Web/Desktop; choose actual continuity route before running',
   'configuration_strategy': {'main_model': 'deepseek-flash through native DeepSeek provider', 'reasoning': 'llm-deepseek.reasoningEffort high and verify enabled thinking on wire',
      'service_tier': 'provider default; record actual', 'fallback_policy': 'Inspect composed preset/client tree and every generation role; no alternate model'},
   'isolated_profile_or_home': 'Fresh DSH_HOME per run, own profile patch and no inherited home overlays, inside whole-process sandbox',
   'documented_commands_not_run': ['dsh --version', 'dsh --help', 'dsh --profile headless --dump-config', 'dsh --profile headless "<public task prompt>"', 'dsh web'],
   'followup_method': 'Web persisted session supports task continuation; official SDK/ACP profiles exist. Headless one-shot alone does not establish cross-device continuity',
   'log_usage_export_method': 'Persisted Session log + stdout/stderr + provider usage/billing; headless derives completion from durable turn/end. Installed retrieval mechanism unverified',
   'configurable_auxiliary_models': 'Inspect composed agent preset/client configuration and delegated children; pin all configurable generation to deepseek-flash',
   'exceptions': ['Default workspace-write policy does not confine reads/network; external process isolation required', 'Default session-log upload and feedback-gated OTel are separate egress paths; inspect and freeze consent/network configuration before execution', 'Unconfigurable safety/embedding services must be recorded without disabling safety'],
   'required_access': ['DeepSeek API account/key (user confirmed possession)', 'Protected provisioning into isolated runtime', 'Installed official dsh release and selected Web/Desktop path'],
   'blockers': ['dsh_not_found_in_PATH','deepseek_key_not_provisioned_to_experiment'] + common_blockers,
   'source_keys': ['dsh_cli','dsh_cli_reference','dsh_providers','dsh_web','deepseek_thinking']
 }
}

for family, data in details.items():
    path = ROOT / f'records/adapter_{family}.json'
    adapter = json.loads(path.read_text())
    adapter.update(data)
    adapter.update({
      'updated_at_utc': NOW, 'record_completion': 'preflight_fields_populated_with_evidence_and_explicit_blockers',
      'launch_command_verified': None, 'stop_command_verified': None,
      'operational_launch_verified': False, 'operational_stop_verified': False,
      'model_verification_method': 'Before and throughout execution retain actual request/response or trusted provider routing evidence for main, child and auxiliary calls; capture alias/version/date; stop on mismatch',
      'billing': {'source': 'user subscription' if family == 'codex' else 'user DeepSeek API billing', 'account_category': 'ChatGPT subscription, exact plan unverified' if family == 'codex' else 'API key account, balance/limits unverified', 'budget_authorized': False, 'external_tool_costs': 'none incurred; future endpoints/resources must be specified'},
      'workspace_and_session_ownership': 'Each run gets a new public-only workspace and fresh subject session; no coordinator history, prior grades, private tests or shared memory. Execution host still to freeze.',
      'evaluator_isolation_method': 'Bubblewrap synthetic mount/PID probe passed locally; production product/auth/tools/network isolation not yet verified. Mount only public task directory and minimal runtime; private evaluator and all coordinator state absent.',
      'evaluator_isolation_verified': False,
      'network': {'planned_inference_endpoint': 'OpenAI subscription route; exact approved endpoint pending' if family == 'codex' else 'https://api.deepseek.com', 'tool_egress_allowlist': 'task-specific; not frozen; no real external side effects', 'controlled_fixture_scope': 'loopback service requires deliberate reachability within isolated runtime; never publish it by default'},
      'cancellation_plan': 'Record exact process/session/job identity; request product cancellation, then verify descendants/remote tasks inactive. A local client exit or closed connection is not evidence of cancellation. Specific installed control still unverified.',
      'sources': [{'url': sources[k], 'evidence_level': 'official_statement', 'checked_on_client_date': '2026-10-24'} for k in data['source_keys']],
      'runtime_evidence': ['state/evidence/local_cli_probes.json'] if family == 'codex' else ['state/evidence/preflight.json'],
      'readiness_approved': False,
      'scope_caution': 'Local CLI absence is an environment blocker, not a whole-family capability judgment. No withdrawn V1 grade inherited.'
    })
    save(path, adapter)

with (ROOT / 'records/availability.csv').open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['family','surface','version','model_available','desktop_mobile_cloud_access','billing_source','adapter_verified','blockers'])
    writer.writeheader()
    for family, data in details.items():
        writer.writerow({'family': family, 'surface': data['surface'], 'version': data['version'] or '',
          'model_available': 'unverified_no_model_request', 'desktop_mobile_cloud_access': 'user_devices_and_connected_routes_pending',
          'billing_source': 'user_confirmed_existing_subscription' if family == 'codex' else 'user_confirmed_DeepSeek_API_key_possession_not_provisioned',
          'adapter_verified': 'partial_cli_auth_only' if family == 'codex' else 'no_runtime_documented_only',
          'blockers': ';'.join(data['blockers'])})

auth_path = ROOT / 'records/authorization.json'
auth = json.loads(auth_path.read_text())
auth.update({'updated_at_utc': NOW,
 'confirmed_resources': {'codex': {'account_type': 'user existing subscription', 'cli_login_status': 'Logged in using ChatGPT', 'exact_plan_and_remaining_quota': None},
                         'deepseek': {'account_type': 'user API account/key available', 'key_provisioned_to_experiment': False, 'account_balance': None}},
 'confirmation_evidence': {'source': 'human user in coordination chat', 'quote': 'codex，你现在用的就是我的订阅服务，deepseek模型我有api和key'},
 'approved_scope': {'pilot_only': True, 'planned_product_runs': 24, 'variant': 'v1', 'repeat': 1, 'formal_216_authorized': False},
 'pending_fields': ['pilot_budget_currency','pilot_budget_amount','subscription_credits_limit','cloud_resource_limit','per_run_wall_clock_cap_seconds','concurrency_limit','allowed_accounts_surfaces'],
 'note': 'User confirmed subscription and API key possession. No quantified fee/quota cap or device/entry agreement yet; do not interpret possession as unlimited execution authorization. No secret value stored.'})
save(auth_path, auth)

order = list(csv.DictReader((ROOT / 'pilot_order.csv').open()))
assert len(order) == 24
assert {(x['family'], x['task']) for x in order} == {(f, f'W{i}') for f in details for i in range(1,7)}
assert all(x['variant'] == 'v1' and x['repeat'] == '1' for x in order)
save(ROOT / 'records/pilot_readiness.json', {
 'at_utc': NOW, 'status': 'held_before_subject_session_creation', 'planned_cases': 24,
 'order_source': 'pilot_order.csv', 'pilot_order_sha256': hashlib.sha256((ROOT/'pilot_order.csv').read_bytes()).hexdigest(),
 'queue_validated': True, 'new_subject_sessions_created': 0, 'prepared_run_workspaces': 0,
 'preconditions': ['Explicit budget/quota/time/concurrency/cloud limits', 'Four effective fixed-model adapters verified', 'Public-only process/tool/read/egress isolation verified', 'W5/W6 devices and lifecycle controls ready'],
 'formal_216_authorized': False
})

for name, event in [
 ('failures.jsonl', {'type':'preflight_documentation_fetch_failure','url':'https://hermes-agent.nousresearch.com/docs/user-guide/features/profiles/','error':'404','resolution':'Followed official navigation to /docs/user-guide/profiles; fetched successfully','product_run_failure':False}),
 ('costs.jsonl', {'type':'subject_experiment_cost_checkpoint','product_runs':0,'subject_model_calls':0,'experiment_incremental_fee':0,'cloud_resources_started':0,'coordination_chat_usage':'existing subscription usage not quantified; excluded from subject runtime comparison'}),
 ('human_interventions.jsonl', {'type':'execution_condition_clarification','actor':'human user','confirmed':['Codex existing subscription','DeepSeek API/key possession'],'task_rescue':False,'unresolved':['budget/quota caps','devices/surfaces','time/concurrency/cloud limits']})
]:
    with (ROOT / 'records' / name).open('a') as f:
        f.write(json.dumps({'at_utc': NOW, **event}, ensure_ascii=False) + '\n')

status_path = ROOT / 'state/status.json'
status = json.loads(status_path.read_text())
status.update({'updated_at_utc': NOW, 'package_status': 'preflight_recorded_execution_gates_pending',
 'readiness': 'not_ready_budget_devices_installed_adapters_effective_models_isolation_pending',
 'adapter_records': {'populated':4, 'operationally_verified':0, 'codex_cli_auth_verified':True, 'records':[f'records/adapter_{f}.json' for f in details]},
 'account_resources': {'codex_subscription_user_confirmed':True,'codex_cli_chatgpt_login_verified':True,'deepseek_key_possession_user_confirmed':True,'deepseek_key_provisioned_to_experiment':False},
 'evaluator_isolation': {'status':'synthetic_probe_passed_product_runtime_unverified','record':'state/evidence/isolation_probe.json','production_verified':False},
 'subject_product_runs':0, 'paid_model_calls':0,
 'accounting': {'cost_log':'records/costs.jsonl','failure_log':'records/failures.jsonl','human_interventions_log':'records/human_interventions.jsonl','coordination_usage_separate':True},
 'pilot': {'planned_runs':24,'started_runs':0,'completed_runs':0,'failed_runs':0,'status':'not_started_gates_pending','queue_record':'records/pilot_readiness.json'},
 'blockers': ['No approved pilot spending/subscription consumption cap or time/concurrency/cloud limits','W5/W6 devices and actual connected family entry routes unspecified','OpenClaw/Hermes/DSH not found in local PATH; no installed release verified','DeepSeek key not provisioned into isolated runtime','Main/child/auxiliary effective fixed-model requests not verified','Whole-product evaluator isolation, egress and cancellation not verified'],
 'next_actions': ['Resolve execution conditions with user; record resource availability without secrets','Provision selected official releases and protected credentials in isolated experiment runtime','Verify each adapter effective model/reasoning/tier, allowed egress, cancellation and evidence retrieval','Use prepare_run.py for fresh public workspaces and new subject sessions; follow pilot_order.csv for only 24 v1/r1 cases','Keep raw failures/usage/interventions; report pilot cost and gaps before any formal expansion']})
status['completed'] += ['four adapter records populated with official sources and explicit runtime blockers','Codex 0.163.0 and ChatGPT login verified without inference','synthetic public-only Bubblewrap mount/PID probe passed; product isolation still pending','24-case v1/r1 pilot order validated; no subject sessions started','user-confirmed subscription/API resource availability recorded without secrets']
save(status_path, status)
with (ROOT / 'state/events.jsonl').open('a') as f:
    f.write(json.dumps({'at_utc':NOW,'type':'adapter_preflight_records_completed','operationally_verified_adapters':0,'populated_adapters':4,'subject_runs_started':0,'paid_subject_model_calls':0,'pilot_held':True},ensure_ascii=False)+'\n')
print(json.dumps({'four_adapter_records_populated':True,'codex_cli_auth_verified':True,'isolation_probe_passed':isolation['exit_code']==0,'production_isolation_verified':False,'pilot_queue_cases':len(order),'subject_runs_started':0},ensure_ascii=False,indent=2))
