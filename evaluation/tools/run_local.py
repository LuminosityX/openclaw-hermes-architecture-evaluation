#!/usr/bin/env python3
"""Run bounded OpenClaw pilots using an existing read-only installation on Linux."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid

from suite import load_matrix

ROOT = Path(__file__).resolve().parents[2]


def runtime_role(build,target,allow_historical=False):
    matches=build.get('version')==target['version'] and build.get('commit')==target['source_commit']
    if matches:
        return 'current-stable-pilot'
    if allow_historical:
        return 'historical-bootstrap-only'
    raise ValueError('Runtime differs from the pinned current stable release '+target['version']+'; use --allow-historical-bootstrap only for historical harness checks')


def decode_report(stdout):
    final=None
    checkpoints={}
    adapter_observations={}
    for line in stdout.splitlines():
        try:
            value=json.loads(line)
        except ValueError:
            continue
        if value.get('product')!='openclaw':
            continue
        if value.get('kind')=='adapter-validation-checkpoint':
            record=value['observation']
            adapter_observations[(record['scenario_id'],record['unit'])]=record
        elif value.get('kind')=='arm-checkpoint':
            study=checkpoints.setdefault(value['study'],dict(study=value['study'],status='recovered-checkpoints',planned_arms=value['planned_arms'],arms=[]))
            study['arms'].append(value['arm'])
        elif isinstance(value.get('studies'),list):
            final=value
    for study in checkpoints.values():
        study['complete']=len(study['arms'])==study['planned_arms']
        study['valid']=all(a.get('valid') for a in study['arms'])
    if final is not None:
        existing={s['study']:s for s in final['studies']}
        for key,study in checkpoints.items():
            if key not in existing:
                final['studies'].append(study)
                final['checkpoint_recovery_used']=True
        if adapter_observations:
            existing={(r['scenario_id'],r['unit']) for r in final.get('observations',[])}
            final.setdefault('observations',[]).extend(r for key,r in adapter_observations.items() if key not in existing)
        return final
    return dict(kind='pilot-aborted',product='openclaw',studies=list(checkpoints.values()),observations=list(adapter_observations.values()),
                harness_error='Inner namespace exited before publishing a final report; complete arm checkpoints are retained')


def sandbox_command(runtime_modules, node, tmpfs_mib, driver_args, ssh_backend=False,driver='pilot.py',relay_socket=None,task_input=None):
    namespaces=['--unshare-pid','--unshare-net','--unshare-ipc','--unshare-uts','--unshare-cgroup'] if ssh_backend else ['--unshare-all']
    capabilities=['--cap-add','CAP_SETUID','--cap-add','CAP_SETGID','--cap-add','CAP_SYS_CHROOT'] if ssh_backend else []
    command = ['bwrap', *namespaces, '--die-with-parent', '--new-session', '--clearenv', '--cap-drop', 'ALL', *capabilities,
               '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin',
               '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
               '--proc', '/proc', '--dev', '/dev', '--size', str(tmpfs_mib * 1024**2), '--tmpfs', '/scratch',
               '--symlink', 'scratch/tmp', '/tmp', '--symlink', 'scratch/home', '/root',
               '--symlink', 'scratch/run', '/run',
               '--ro-bind', str(runtime_modules), '/runtime/node_modules',
               '--ro-bind', str(node), '/toolchain/node', '--symlink', '/toolchain/node', '/toolchain/nodejs',
               '--ro-bind', str(ROOT / 'evaluation/runner'), '/driver',
               '--chdir', '/scratch', '--setenv', 'PATH', '/toolchain:/usr/bin:/bin',
               '--setenv', 'HOME', '/root', '--setenv', 'TMPDIR', '/tmp',
               '--setenv', 'XDG_CACHE_HOME', '/scratch/cache', '--setenv', 'PYTHONDONTWRITEBYTECODE', '1',
               '--setenv', 'NODE_DISABLE_COMPILE_CACHE', '1', '--setenv', 'JITI_CACHE_DIR', '/scratch/cache/jiti']
    for name in ['/etc/passwd', '/etc/group', '/etc/localtime', '/etc/ssl/certs']:
        if Path(name).exists():
            command += ['--ro-bind', name, name]
    if relay_socket:
        command += ['--ro-bind',str(relay_socket),'/relay/provider.sock']
    if task_input:
        command += ['--ro-bind',str(task_input),'/task/input.json']
    return command + ['--', '/usr/bin/python3', '/driver/'+driver, *driver_args]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-modules', type=Path, required=True)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--study', choices=['smoke', 'ARC-01', 'ARC-02', 'ARC-03', 'first-wave','source-followup','SRC-01','SRC-02','SRC-03','SRC-04'], default='first-wave')
    parser.add_argument('--blocks', type=int, default=2)
    parser.add_argument('--tmpfs-mib', type=int, default=64)
    parser.add_argument('--memory-mib', type=int, default=1024)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--ssh-backend', action='store_true', help='Use an owned ephemeral loopback SSH backend; no Docker images')
    parser.add_argument('--allow-historical-bootstrap',action='store_true',help='Explicitly label a non-current runtime as harness bootstrap only')
    parser.add_argument('--hosted-profile',action='store_true',help='Allow an explicit larger-memory profile on disposable hosted workers')
    parser.add_argument('--model-validation',action='store_true',help='Validate real-provider plumbing; contributes no full-campaign coverage')
    parser.add_argument('--relay-socket',type=Path,help='Host-only fixed-provider Unix relay; no key enters the namespace')
    parser.add_argument('--adapter-validation',choices=['REL-14','REL-15','EXT-08'],help='Validate candidate adapters; contributes no full-campaign coverage')
    parser.add_argument('--task-input',type=Path,help='Public task specification only; hidden oracle remains on the host')
    args = parser.parse_args()
    if args.model_validation and (not args.hosted_profile or not args.relay_socket or not args.relay_socket.is_socket()):
        parser.error('Real-model plumbing validation requires the hosted profile and an existing Unix relay socket')
    if args.model_validation and args.adapter_validation:
        parser.error('Choose a single validation driver')
    if args.task_input and (args.model_validation or args.adapter_validation or not args.relay_socket or not args.task_input.is_file()):
        parser.error('Native task requires its public input and a fixed-provider relay, with no other validation mode')
    if not 16 <= args.tmpfs_mib <= 128 or not 1 <= args.blocks <= 4 or not 1 <= args.timeout <= 1200:
        parser.error('Bounded pilot limits: 16..128 MiB tmpfs, 1..4 blocks, 1..1200 seconds')
    maximum_memory=4096 if args.hosted_profile else 1536
    if not 512 <= args.memory_mib <= maximum_memory:
        parser.error(f'Pilot memory budget must be 512..{maximum_memory} MiB for this explicit profile')
    modules = args.runtime_modules.resolve()
    node = args.node.resolve()
    build_path = modules / 'openclaw/dist/build-info.json'
    if not build_path.is_file() or not node.is_file() or not shutil.which('bwrap'):
        parser.error('Existing built OpenClaw installation, compatible Node and bwrap are required; no auto-install')
    if args.output.exists():
        parser.error('Output path already exists; preserve it and select a new path')
    build = json.loads(build_path.read_text())
    target=load_matrix()['target']
    try:
        role=runtime_role(build,target,args.allow_historical_bootstrap)
    except ValueError as error:
        parser.error(str(error))
    lock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        lock.bind('\0openclaw-architecture-pilot-'+str(os.getuid()))
    except OSError:
        parser.error('Another bounded pilot owns the host experiment lock; do not overlap measurements')
    controller_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in [Path(__file__), *sorted(p for p in (ROOT/'evaluation/runner').iterdir() if p.suffix in {'.py','.mjs'})]}
    group = Path('/sys/fs/cgroup/system.slice') / ('openclaw-evaluation-' + uuid.uuid4().hex[:12] + '.scope')
    process = None
    timed_out=False
    started = time.monotonic()
    try:
        group.mkdir()
        for field, value in {'memory.max':args.memory_mib*1024**2, 'memory.swap.max':0,
                             'pids.max':128, 'cpu.max':'200000 100000', 'memory.oom.group':1}.items():
            (group / field).write_text(str(value))
        driver='task_unit.py' if args.task_input else 'model_validation.py' if args.model_validation else 'adapter_validation.py' if args.adapter_validation else 'pilot.py'
        driver_args=[] if args.model_validation or args.task_input else ['--case',args.adapter_validation] if args.adapter_validation else ['--study',args.study,'--blocks',str(args.blocks),*(['--ssh-backend'] if args.ssh_backend else [])]
        command = sandbox_command(modules,node,args.tmpfs_mib,driver_args,args.ssh_backend,driver=driver,relay_socket=args.relay_socket,task_input=args.task_input)
        def enter_group():
            (group / 'cgroup.procs').write_text(str(os.getpid()))
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True, preexec_fn=enter_group)
        try:
            stdout, stderr = process.communicate(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out=True
            (group / 'cgroup.kill').write_text('1')
            stdout, stderr = process.communicate(timeout=10)
        source_run=args.study=='source-followup' or args.study.startswith('SRC-')
        if len(stdout.encode()) > (2 if source_run else 1)*1024**2 or len(stderr.encode()) > 128*1024:
            raise RuntimeError('Pilot exceeded its persisted evidence budget; no raw output retained')
        report=decode_report(stdout)
        if timed_out:
            report['harness_error']='Whole-run time budget exhausted; completed arm checkpoints retained'
        if report.get('harness_error'):
            report['stderr_tail']=stderr[-8000:]
            report['whole_run_timeout']=timed_out
        report.update(runtime_identity=build, runtime_build_info_sha256=hashlib.sha256(build_path.read_bytes()).hexdigest(),
                      evaluation_role=role,campaign_target=target,
                      execution_budget=dict(profile='hosted' if args.hosted_profile else 'local',
                          memory_limit_bytes=args.memory_mib*1024**2,swap_limit_bytes=0,
                          cpu_quota_cores=2,pids_limit=128,timeout_seconds=args.timeout),
                      controller_sha256=controller_hashes,
                      wrapper_exit_code=process.returncode, whole_run_seconds=round(time.monotonic()-started,3),
                      storage_policy=dict(shared_installation_copied=False, downloads=0,
                          tmpfs_limit_bytes=args.tmpfs_mib*1024**2, swap_limit_bytes=0,
                          persisted_report_limit_bytes=1024**2, runtime_state_retained=False),
                      whole_run_cgroup=dict(memory_peak_bytes=int((group/'memory.peak').read_text()),
                          memory_events=(group/'memory.events').read_text(),
                          pids_events=(group/'pids.events').read_text(),cpu_stat=(group/'cpu.stat').read_text()))
        encoded = (json.dumps(report,ensure_ascii=False,indent=None if source_run else 2,separators=(',',':') if source_run else None)+'\n').encode()
        if len(encoded) > 1024**2:
            raise RuntimeError('Summary exceeds the 1 MiB evidence budget')
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output/'summary.json').write_bytes(encoded)
        print(json.dumps(dict(report=str(args.output/'summary.json'), bytes=len(encoded),
                              exit_code=process.returncode, studies=[dict(study=s.get('study'),status=s.get('status'),valid=s.get('valid')) for s in report.get('studies',[])],
                              storage_policy=report['storage_policy']),ensure_ascii=False))
        if process.returncode or report.get('harness_error'):
            raise RuntimeError('Pilot reported a harness/validity failure; inspect the bounded summary')
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f'FAIL: {error}\n')
    finally:
        lock.close()
        if group.exists():
            if (group/'cgroup.procs').read_text().strip():
                (group/'cgroup.kill').write_text('1')
            for _ in range(30):
                try:
                    group.rmdir()
                    break
                except OSError:
                    time.sleep(.05)


if __name__ == '__main__':
    main()
