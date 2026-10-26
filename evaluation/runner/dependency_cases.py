"""Native managed plugin dependency reconstruction and failed-install repair."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

from operation_fixture import OperationFixture
from package_registry_fixture import PackageRegistry,PLUGIN,VERSION,plugin_archive
import pilot
import service_path_cases as service

FAMILIES={'REL-07':['empty','verified-cache','missing','checksum'],'REL-12':['partial','checksum','cache-unavailable','interrupted']}
SCENARIOS={f'{family}-S{i:02}':mode for family,modes in FAMILIES.items() for i,mode in enumerate(modes,1)}


def environment_selfcheck():
    npm=Path('/toolchain/npm')
    if not npm.is_file():raise RuntimeError('The explicit hosted npm toolchain mount is missing')
    execution=subprocess.run([str(npm),'--version'],capture_output=True,text=True,timeout=15)
    if execution.returncode:raise RuntimeError('Owned npm executable failed its positive control')
    return dict(npm_version=execution.stdout.strip(),registry='Owned loopback registry only; namespace has no outward route',
        installation_scope='Native managed plugin npm dependencies; the pinned core is shared read-only, not reinstalled or copied',host_dependency_mounts=False)


def environment(root,cache):
    return dict(os.environ,OPENCLAW_STATE_DIR=str(root/'state'),OPENCLAW_CONFIG_PATH=str(root/'config.json'),
        OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_DISABLE_BUNDLED_PLUGINS='1',npm_config_registry='http://127.0.0.1:18091',
        npm_config_cache=str(cache),npm_config_fetch_retries='0',npm_config_fetch_timeout='5000',
        npm_config_audit='false',npm_config_fund='false',npm_config_update_notifier='false',npm_config_progress='false')


def command(root,cache,*arguments,timeout=90):
    begin=time.monotonic_ns();execution=subprocess.run([pilot.NODE,pilot.CLI,'plugins',*map(str,arguments)],env=environment(root,cache),capture_output=True,text=True,timeout=timeout)
    return dict(arguments=list(map(str,arguments)),returncode=execution.returncode,stdout=execution.stdout[-8000:],stderr=execution.stderr[-4000:],
        started_monotonic_ns=begin,ended_monotonic_ns=time.monotonic_ns())


def inspect(root,cache):
    result=command(root,cache,'inspect',PLUGIN,'--json',timeout=35)
    try:payload=json.loads(result['stdout'])
    except ValueError:payload=None
    result['payload']=payload
    return result


def installed(result):
    payload=result.get('payload')
    return bool(isinstance(payload,dict) and isinstance(payload.get('install'),dict) and payload['install'].get('installPath'))


def configure(root):
    config=service.configure(root);config['tools']['allow'].append('dependency_probe');pilot.save(root/'config.json',config);return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];registry=PackageRegistry();fixture=OperationFixture();gateway=None;child=None;assertions=[];metadata={};commands=[]
    token='PILOT_DEPENDENCY_'+scenario.replace('-','_')+'_U'+str(unit)
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-plugin-install-inspect-and-enable','independent-owned-registry-events-and-integrity','actual-native-imported-dependency-and-tool-effect','bounded-owned-filesystem']))
    try:
        configure(root);archive=root/'owned-plugin.tgz';data=plugin_archive();archive.write_bytes(data);cache=root/'owned-npm-cache'
        metadata.update(plugin_archive_sha256=hashlib.sha256(data).hexdigest(),dependency_archive_sha256=hashlib.sha256(registry.raw).hexdigest(),
            raw_archive_bytes=len(data)+len(registry.raw),host_environment_references_used=False)
        if mode=='verified-cache':
            seed=root/'owned-cache-seed';configure(seed)
            seeded=command(seed,cache,'install',archive,'--accept-capabilities');commands.append(seeded)
            if seeded['returncode'] or not installed(inspect(seed,cache)):raise RuntimeError('Verified native dependency-cache seed did not publish a valid install')
            metadata['cache_seed_tarball_fetched']=registry.tarball_started.is_set()
            if not metadata['cache_seed_tarball_fetched']:raise RuntimeError('Cache seed did not fetch the independently verified owned tarball')
            shutil.rmtree(seed);registry.mode='offline'
        elif mode in {'missing','checksum','partial'}:registry.mode=mode
        elif mode=='cache-unavailable':cache=Path('/runtime/node_modules/owned-readonly-evaluation-cache')
        event_start=len(registry.events)
        if mode=='interrupted':
            registry.mode='gate';registry.release.clear();registry.tarball_started.clear()
            child=subprocess.Popen([pilot.NODE,pilot.CLI,'plugins','install',str(archive),'--accept-capabilities'],env=environment(root,cache),
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
            deadline=time.monotonic()+60
            while time.monotonic()<deadline and not registry.tarball_started.is_set() and child.poll() is None:time.sleep(.05)
            if not registry.tarball_started.is_set() or child.poll() is not None:raise RuntimeError('Native dependency installer did not reach the actual gated tarball publication boundary')
            stages=[str(p.relative_to(root)) for p in root.rglob('*') if 'stage' in p.name.lower()][:12]
            os.killpg(child.pid,signal.SIGKILL);stdout,stderr=child.communicate(timeout=8);registry.release.set()
            initial=dict(returncode=child.returncode,stdout=stdout[-6000:],stderr=stderr[-3000:],owned_staging_paths=stages,
                actual_dependency_download_gated=True,kill_monotonic_ns=time.monotonic_ns());child=None
        else:
            env=environment(root,cache)
            if mode=='verified-cache':env['npm_config_offline']='true'
            begin=time.monotonic_ns();execution=subprocess.run([pilot.NODE,pilot.CLI,'plugins','install',str(archive),'--accept-capabilities'],env=env,capture_output=True,text=True,timeout=90)
            initial=dict(returncode=execution.returncode,stdout=execution.stdout[-8000:],stderr=execution.stderr[-4000:],started_monotonic_ns=begin,ended_monotonic_ns=time.monotonic_ns())
        commands.append(initial);initial_inspection=inspect(root,cache);metadata['initial_inspection']=initial_inspection
        intervention_events=registry.events[event_start:];metadata['fault_phase_registry_events']=intervention_events
        if mode in {'missing','checksum','partial','interrupted'} and not any(e['mode']==('gate' if mode=='interrupted' else mode) for e in intervention_events):
            raise RuntimeError('Declared native dependency fault was not independently reached')
        if mode in {'empty','verified-cache'}:
            check('native-reconstruction-succeeds-in-declared-cache-condition',initial['returncode']==0 and installed(initial_inspection))
            if mode=='verified-cache':check('verified-cache-reconstruction-needs-no-registry-request',not intervention_events)
        else:
            check('faulted-install-not-reported-successful',initial['returncode']!=0)
            check('incomplete-dependency-generation-not-published',not installed(initial_inspection))
        # Repair is always native: restore the owned server/cache, then retry the
        # same immutable archive. No copied module tree or hand-edited registry.
        registry.mode='healthy';registry.release.set();cache=root/'owned-npm-cache'
        if initial['returncode']!=0 or not installed(initial_inspection):
            repaired=command(root,cache,'install',archive,'--accept-capabilities');commands.append(repaired)
            metadata['repair_command']=repaired
        final_inspection=inspect(root,cache);metadata['final_inspection']=final_inspection
        if not installed(final_inspection):raise RuntimeError('Native healthy repair has no actual published installation')
        enabled=command(root,cache,'enable',PLUGIN,'--accept-capabilities');commands.append(enabled)
        if enabled['returncode']:raise RuntimeError('Native installed dependency plugin cannot be enabled')
        gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready()
        control=token+'_CONTROL';fixture.register(control)
        if not gateway.request(control)['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Native ordinary task control failed after the install experiment')
        fixture.plan(token,'dependency_probe',dict(token=token),'OWNED_DEPENDENCY_1.0.0');result=gateway.request(token)
        if not fixture.tool_returns.get(token):raise RuntimeError('Native dependency tool did not return an independently observed result')
        row.update(native_invoked=True,fixture_validated=True)
        check('actual-owned-dependency-import-and-native-effect-after-reconstruction',result['accepted'] and fixture.receipts.get(token)==1)
        imported=final_inspection['payload']['install']['installPath'];package=Path(imported)
        check('published-plugin-remains-inside-owned-state',package.is_relative_to(root/'state'))
        metadata.update(mode=mode,task=result,native_tool_return=fixture.tool_returns.get(token),published_package=str(package.relative_to(root)) if package.is_relative_to(root) else str(package),
            cache_repair_scope='Only owned loopback package/cache restored; same immutable plugin archive retried through native CLI. No host node_modules, environment credentials or global dependency fallback is supplied.',
            reconstruction_scope='Native managed extension npm dependency installation, not a claim about portable OS native binaries or copying the core installation.')
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,commands=commands,
            independent_registry_events=registry.events,independent_events=fixture.events,independent_receipts=fixture.receipts,
            resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2200],metadata=metadata,commands=commands,independent_registry_events=registry.events)
    finally:
        registry.release.set()
        if child and child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-3000:]
        registry.close();fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
