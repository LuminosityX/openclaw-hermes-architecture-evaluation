"""Isolated Codex runtime wrapper for local adapter development and calibration.

Every run gets its own throwaway CODEX_HOME and workspace directory; the user's
real ~/.codex state, credentials and history are never read or written. The
pinned binary is invoked exactly as documented (`codex exec`, `codex exec
resume`), always with --skip-git-repo-check inside the owned workspace, and the
process group is fully terminated on timeout. Rollout files are read through
independent read-only JSONL parsing; this reader never trusts product APIs for
persistence claims.

This wrapper is development calibration tooling: formal campaign units run the
same controller code on disposable hosted runners with the pinned installation.
"""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

from codex_provider_fixture import ResponsesFixture
from codex_effect_ledger import EffectLedger

CONFIG_TEMPLATE = """\
# Generated for an isolated Codex mechanism run; never written to a real home.
model = "{model}"
model_provider = "fixture"

[model_providers.fixture]
name = "Owned deterministic fixture provider"
base_url = "{base_url}"
env_key = "CODEX_FIXTURE_KEY"
wire_api = "responses"

[sandbox_workspace_write]
network_access = true
"""


class CodexRuntime:
    """One isolated home + workspace + fixture provider, reusable across runs."""

    def __init__(self, codex='codex', root=None, model='fixture-model', sandbox='read-only'):
        self.codex_bin = shutil.which(codex) or codex
        self.root = Path(root or tempfile.mkdtemp(prefix='codex-mechanism-'))
        self.home = self.root / 'codex-home'
        self.workspace = self.root / 'workspace'
        self.home.mkdir(parents=True, exist_ok=True)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.sandbox = sandbox
        self.fixture = ResponsesFixture(model=model).start()
        self.ledger = EffectLedger().start()
        (self.home / 'config.toml').write_text(
            CONFIG_TEMPLATE.format(model=model, base_url=self.fixture.base_url), encoding='utf-8')
        self.env = dict(os.environ)
        self.env.update(CODEX_HOME=str(self.home), CODEX_FIXTURE_KEY=self.fixture.bearer)

    def base_args(self):
        return [self.codex_bin, 'exec', '--skip-git-repo-check', '-s', self.sandbox,
                '-C', str(self.workspace)]

    def run(self, prompt, timeout=60, extra_args=()):
        started = time.monotonic_ns()
        process = subprocess.Popen(
            [*self.base_args(), *extra_args, prompt], env=self.env, cwd=str(self.workspace),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self.kill_process_group(process)
            stdout, stderr = process.communicate()
        return dict(exit=None if timed_out else process.returncode, timed_out=timed_out,
                    stdout=stdout, stderr=stderr,
                    duration_ms=(time.monotonic_ns() - started) // 1_000_000)

    def spawn(self, prompt='-', extra_args=(), json_output=True, hold_stdin=False):
        """Start codex exec without waiting; returns the Popen for boundary kills.

        With the default prompt='-' and hold_stdin, the process boots and waits
        for instructions on stdin that the client never sends: a deterministic
        'request merely received, nothing handed over' admission boundary."""
        args = self.base_args() + list(extra_args)
        if json_output:
            args.append('--json')
        return subprocess.Popen([*args, prompt], env=self.env, cwd=str(self.workspace),
                                stdin=subprocess.PIPE if hold_stdin else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                start_new_session=True)

    def resume(self, prompt, timeout=60, last=True):
        # `codex exec resume` does not accept -s/-C; it locates sessions by cwd
        # and inherits sandbox/model settings from CODEX_HOME/config.toml.
        args = [self.codex_bin, 'exec', 'resume', '--skip-git-repo-check']
        if last:
            args.append('--last')
        started = time.monotonic_ns()
        process = subprocess.Popen([*args, prompt], env=self.env, cwd=str(self.workspace),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   start_new_session=True)
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self.kill_process_group(process)
            stdout, stderr = process.communicate()
        return dict(exit=None if timed_out else process.returncode, timed_out=timed_out,
                    stdout=stdout, stderr=stderr,
                    duration_ms=(time.monotonic_ns() - started) // 1_000_000)

    def spawn_resume(self, prompt, last=True, extra_args=()):
        """Start `codex exec resume` without waiting; returns the Popen for kills."""
        args = [self.codex_bin, 'exec', 'resume', '--skip-git-repo-check']
        if last:
            args.append('--last')
        return subprocess.Popen([*args, *extra_args, prompt], env=self.env, cwd=str(self.workspace),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                start_new_session=True)

    @staticmethod
    def kill_process_group(process):
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()

    # --- independent persistence readers -------------------------------------

    def rollout_paths(self):
        sessions = self.home / 'sessions'
        return sorted(sessions.rglob('*.jsonl')) if sessions.exists() else []

    def read_rollout(self, path):
        records = []
        for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                records.append(dict(unparsed_line=line[:200]))
        return records

    def rollout_digest(self):
        """Independent view of every rollout record type in the owned home."""
        digests = []
        for path in self.rollout_paths():
            records = self.read_rollout(path)
            digests.append(dict(path=str(path.relative_to(self.home)),
                                lines=len(records),
                                types=sorted({str(r.get('type')) for r in records if isinstance(r, dict)}),
                                bytes=path.stat().st_size))
        return digests

    def workspace_files(self):
        return sorted(str(p.relative_to(self.workspace)) for p in self.workspace.rglob('*') if p.is_file())

    def close(self):
        self.fixture.close()
        self.ledger.close()
        shutil.rmtree(self.root, ignore_errors=True)
