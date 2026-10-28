#!/usr/bin/env python3
"""Hosted diagnostic probe: why did sandboxed effect commands miss the ledger?

Runs on the disposable hosted image with the pinned Codex and answers, with
recorded evidence: is curl available inside the sandbox, can the sandboxed
shell reach a loopback HTTP service under sandbox_workspace_write with
network_access=true, does a scripted in-turn exec_command reach the ledger,
and what exact text did the tool output contain. This is diagnostic tooling
only; it produces no campaign observation.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'evaluation' / 'runner'))

from codex_effect_ledger import EffectLedger
from codex_runtime import CodexRuntime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex', required=True)
    parser.add_argument('--output', type=Path,
                        default=Path(os.environ.get('RUNNER_TEMP', '.')) / 'codex-diagnostics.json')
    args = parser.parse_args()
    report = dict(kind='codex-sandbox-diagnostics', development=True,
                  codex_bin=args.codex, kernel=os.uname().release)
    ledger = EffectLedger().start()
    runtime = CodexRuntime(codex=args.codex, sandbox='workspace-write')
    try:
        probe_url = f'http://127.0.0.1:{ledger.port}/count?token=PROBE'
        command = f'curl -s -S -m 10 {probe_url} ; echo CURL_EXIT_$?'

        outside = subprocess.run(['bash', '-lc', command], capture_output=True, text=True, timeout=30)
        report['outside_sandbox'] = dict(exit=outside.returncode,
                                         stdout=outside.stdout[:300], stderr=outside.stderr[:300])

        import tempfile
        probe_home = Path(tempfile.mkdtemp(prefix='codex-diag-home-'))
        probe_home.mkdir(parents=True, exist_ok=True)
        (probe_home / 'config.toml').write_text(
            '[sandbox_workspace_write]\nnetwork_access = true\n', encoding='utf-8')
        env = dict(os.environ, CODEX_HOME=str(probe_home))
        sandboxed = subprocess.run([args.codex, 'sandbox', '--', 'bash', '-lc', command],
                                   capture_output=True, text=True, timeout=60, env=env)
        report['codex_sandbox_command'] = dict(exit=sandboxed.returncode,
                                               stdout=sandboxed.stdout[:300],
                                               stderr=sandboxed.stderr[:300])
        shutil.rmtree(probe_home, ignore_errors=True)

        runtime.fixture.script = [
            {'call': {'name': 'exec_command', 'arguments': {'cmd': command}}},
            {'reply': 'DIAG_FINAL'},
        ]
        turn = runtime.run('Run the requested diagnostic command exactly as instructed.', timeout=180)
        sys.path.insert(0, str(ROOT / 'evaluation' / 'runner'))
        import rel01_cases as rel01
        import rel02_cases as rel02
        records = rel01.rollout_records(runtime)
        calls = rel02.function_call_lines(records, 'PROBE')
        outputs = []
        for call in calls:
            outputs.extend(rel02.function_call_output_lines(records, call.get('call_id')))
        report['in_turn_exec'] = dict(turn_exit=turn['exit'],
                                      function_calls=len(calls),
                                      tool_output_text=rel02.output_text_bounded(outputs, 900),
                                      ledger_requests=len([e for e in ledger.events]))
        report['turn_stderr_tail'] = turn['stderr'][-400:]
    finally:
        runtime.close()
        ledger.close()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
