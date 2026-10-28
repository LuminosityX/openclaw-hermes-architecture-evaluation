"""Development calibration: verify the fixture provider and isolated runtime
against the real pinned Codex binary. This is NOT a formal experiment record.

Checks: (1) a trivial turn completes end-to-end through the fixture provider;
(2) the rollout file independently shows the user input and assistant reply;
(3) `codex exec resume --last` continues the same thread; (4) the --ephemeral
negative control leaves no rollout. Output is a small JSON report.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_runtime import CodexRuntime


def main():
    runtime = CodexRuntime()
    report = dict(kind='codex-adapter-smoke', development_calibration=True,
                  codex=runtime.codex_bin, fixture_base_url=runtime.fixture.base_url)
    try:
        first = runtime.run('Reply with exactly: SMOKE_ONE_OK', timeout=90)
        report['first_run'] = {k: first[k] for k in ('exit', 'timed_out', 'duration_ms')}
        report['first_run']['stdout_tail'] = first['stdout'][-400:]
        report['first_run']['stderr_tail'] = first['stderr'][-600:]
        report['fixture_requests'] = runtime.fixture.requests()
        report['rollouts_after_first'] = runtime.rollout_digest()

        resumed = runtime.resume('Reply with exactly: SMOKE_TWO_OK', timeout=90)
        report['resume_run'] = {k: resumed[k] for k in ('exit', 'timed_out', 'duration_ms')}
        report['resume_run']['stdout_tail'] = resumed['stdout'][-400:]
        report['rollouts_after_resume'] = runtime.rollout_digest()

        ephemeral = runtime.run('Reply with exactly: EPHEMERAL_OK', timeout=90,
                                extra_args=['--ephemeral'])
        report['ephemeral_run'] = {k: ephemeral[k] for k in ('exit', 'timed_out')}
        report['rollouts_after_ephemeral'] = runtime.rollout_digest()
    finally:
        runtime.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
