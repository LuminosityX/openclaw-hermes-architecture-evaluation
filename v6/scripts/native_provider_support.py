"""Prepare the pinned official provider locally before offline Doctor convergence.
Only call for explicitly recorded dependency-preparation/operations profiles;
existing formal/performance profiles and product source are never modified.
"""
import copy, hashlib, json, subprocess, time
from runtime import R, sandbox, save
from run_state_ops import cli


def install_deepseek(run, relay=None):
    source = R / 'runtime/deepseek-provider'
    if not (source / 'openclaw.plugin.json').exists():
        raise RuntimeError('Verify the pinned official provider artifact before installation')
    config_path = run / 'state/openclaw.json'
    original = json.loads(config_path.read_text())
    original_exec = copy.deepcopy(original.get('tools', {}).get('exec'))
    prepared = copy.deepcopy(original)
    # Plugin setup is not the legacy policy test: hold canonical deny during
    # setup, then restore the exact legacy input before Doctor performs migration.
    if original_exec and any(key in original_exec for key in ['security', 'ask']):
        prepared.setdefault('tools', {})['exec'] = {'mode': 'deny'}
    plugin = prepared.setdefault('plugins', {})
    if isinstance(plugin.get('allow'), list) and 'deepseek' not in plugin['allow']:
        plugin['allow'].append('deepseek')
    plugin.setdefault('entries', {}).setdefault('deepseek', {})['enabled'] = True
    save(config_path, prepared)
    command = sandbox(run / 'state', run / 'workspace', 'openclaw', cli('openclaw', [
        'plugins', 'install', '--force', '--accept-capabilities', '/addons/deepseek-provider']),
        relay.socket_dir if relay else None, [(source, '/addons/deepseek-provider', True)])
    begin = time.monotonic()
    with (run / 'provider-install.stdout.log').open('w') as out, (run / 'provider-install.stderr.log').open('w') as err:
        result = subprocess.run(command, stdout=out, stderr=err, stdin=subprocess.DEVNULL, timeout=90)
    current = json.loads(config_path.read_text())
    # Model choice, endpoint, reasoning and effective 64K budget remain explicit.
    current['models'] = original['models']
    current['agents'] = original['agents']
    if original_exec is not None:
        current.setdefault('tools', {})['exec'] = original_exec
    save(config_path, current)
    record = dict(command=command, exit_code=result.returncode, seconds=time.monotonic()-begin,
                  official_package='@openclaw/deepseek-provider@2026.10.6',
                  artifact_metadata='evidence/deepseek-provider-registry-metadata.json',
                  install_mode='native managed copy from verified local official artifact, not an external source link',
                  original_exec_policy_restored=current.get('tools', {}).get('exec') == original_exec,
                  model_configuration_preserved=current['models'] == original['models'] and current['agents'] == original['agents'],
                  package_manifest_sha256=hashlib.sha256((source / 'openclaw.plugin.json').read_bytes()).hexdigest())
    save(run / 'native-provider-preparation.json', record)
    if result.returncode:
        raise RuntimeError('Official local provider installation failed; inspect native logs')
    return record
