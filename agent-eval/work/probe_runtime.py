"""No-inference, offline product help/configuration probes in narrow mounts."""
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/root/Documents/Codex/2026-10-24/agent-root-downloads-1023magnitude-agent-eval/work/subject-runtime')
EVIDENCE = Path('/root/Downloads/1023magnitude/agent_eval_handoff/state/evidence')
family, *arguments = sys.argv[1:]
allowed = arguments[-1:] in [['--help'], ['--version'], ['--dump-config'], ['--dump-default-config']]
if family not in ['openclaw', 'dsh'] or not allowed:
    raise SystemExit('Only version/help/unbooted config dump probes are allowed.')
entry = '/runtime/openclaw/node_modules/openclaw/openclaw.mjs' if family == 'openclaw' else '/runtime/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js'
command = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
           '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib',
           '--symlink', 'usr/lib64', '/lib64', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
           '--tmpfs', '/root', '--bind', str(ROOT), '/runtime', '--chdir', '/runtime',
           '--setenv', 'PATH', '/runtime/node-v24.22.1-linux-x64/bin:/usr/bin:/bin',
           '--setenv', 'OPENCLAW_STATE_DIR', '/runtime/probe-state/openclaw',
           '--setenv', 'OPENCLAW_CONFIG_PATH', '/runtime/probe-state/openclaw/openclaw.json',
           '--setenv', 'DSH_HOME', '/runtime/probe-state/dsh']
for path in ['/etc/alternatives', '/etc/ssl/certs', '/etc/passwd', '/etc/group']:
    if Path(path).exists():
        command += ['--ro-bind', path, path]
command += ['--', 'node', entry, *arguments]
result = subprocess.run(command, capture_output=True, text=True, timeout=30)
record = {'at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'family': family,
          'arguments': arguments, 'scope': 'offline_help_or_unbooted_config_only_no_model',
          'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
name = family + '_' + '_'.join(word.lstrip('-') for word in arguments) + '.json'
destination = EVIDENCE / name
if destination.exists():
    raise SystemExit('Existing probe record preserved; choose a new attempt identity before retrying.')
destination.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
print(result.stdout)
if result.stderr:
    print(result.stderr, file=sys.stderr)
raise SystemExit(result.returncode)
