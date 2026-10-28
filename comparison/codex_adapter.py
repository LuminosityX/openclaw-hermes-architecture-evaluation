"""Codex comparison adapter: profile A (codex exec --json / resume), standalone.

Comparison-profile wrapper per comparison/execution-protocol.md §2: one fresh
isolated home, workspace, credentials and process group per unit; the product
binary is started exactly through its documented entry points. The adapter
never retries, cancels, resumes or deduplicates on the product's behalf —
those behaviours belong to the product under test.
"""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

CONFIG_TEMPLATE = """\
# Isolated per-unit comparison home; never written to a real user home.
model = "{model}"
model_provider = "m"

[model_providers.m]
name = "Comparison model fixture M"
base_url = "{base_url}"
env_key = "COMPARISON_M_KEY"
wire_api = "responses"
"""


class CodexAdapter:
    def __init__(self, codex_bin, unit_id, model_base_url, model='fixture-model',
                 sandbox='read-only', root=None):
        self.codex_bin = str(codex_bin)
        self.unit_id = unit_id
        self.root = Path(root or tempfile.mkdtemp(prefix=f'comparison-codex-{unit_id}-'))
        self.home = self.root / 'codex-home'
        self.workspace = self.root / 'workspace'
        self.home.mkdir(parents=True, exist_ok=True)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.sandbox = sandbox
        (self.home / 'config.toml').write_text(
            CONFIG_TEMPLATE.format(model=model, base_url=model_base_url), encoding='utf-8')
        self.env = dict(os.environ)
        self.env.update(CODEX_HOME=str(self.home), COMPARISON_M_KEY='fixture-key')

    def _args(self):
        return [self.codex_bin, 'exec', '--skip-git-repo-check', '-s', self.sandbox,
                '-C', str(self.workspace), '--json']

    def spawn(self, prompt):
        """Start a task without waiting; returns the Popen for fault injection."""
        return subprocess.Popen([*self._args(), prompt], env=self.env,
                                cwd=str(self.workspace), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True)

    def spawn_resume(self, prompt):
        args = [self.codex_bin, 'exec', 'resume', '--skip-git-repo-check', '--last']
        return subprocess.Popen([*args, prompt], env=self.env, cwd=str(self.workspace),
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, start_new_session=True)

    def run(self, prompt, timeout=180.0):
        return self._wait(self.spawn(prompt), timeout)

    def resume(self, prompt, timeout=180.0):
        return self._wait(self.spawn_resume(prompt), timeout)

    @staticmethod
    def _wait(process, timeout):
        started = time.monotonic_ns()
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            CodexAdapter.kill_group(process)
            stdout, stderr = process.communicate()
        return dict(exit=None if timed_out else process.returncode, timed_out=timed_out,
                    stdout=stdout, stderr=stderr,
                    duration_ms=(time.monotonic_ns() - started) // 1_000_000)

    @staticmethod
    def kill_group(process):
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()

    def residual_processes(self):
        """Owned processes still alive under this unit's root (best effort)."""
        output = subprocess.run(
            ['ps', '-eo', 'pid=,args='], capture_output=True, text=True).stdout
        return [line.strip() for line in output.splitlines() if str(self.root) in line]

    def rollout_paths(self):
        sessions = self.home / 'sessions'
        return sorted(sessions.rglob('*.jsonl')) if sessions.exists() else []

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)
