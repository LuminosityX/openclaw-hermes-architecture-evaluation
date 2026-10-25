"""Release redundant HISTORICAL evaluation dependency copies, preserving evidence.

No product runs are started. Native state/results, source and lock manifests are
kept. Removed dependency generations must be reinstalled before historical replay.
"""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path

R=Path('/root/output/oc-hermes-execution-20261024-v6')
OLD=Path('/root/Documents/Codex/2026-10-24/agent-root-downloads-1023magnitude-agent-eval/work')
ROOTS=[Path('/root/output/oc-hermes-comparison-20261024-v5'),OLD/'w5',OLD/'effective-config-preflight',OLD/'codex-daemon-lifecycle-preflight',Path('/root/Downloads/1023magnitude/agent_eval_handoff/runs')]
OUT=R/'evidence/historical-dependency-reclamation.json'

def write(path,obj):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2));tmp.replace(path)

def active_references():
    ancestors={os.getpid()};pid=os.getppid()
    while pid>1:
        ancestors.add(pid)
        try:pid=int(next(l for l in Path(f'/proc/{pid}/status').read_text().splitlines() if l.startswith('PPid:')).split()[1])
        except (OSError,StopIteration):break
    active=[]
    for item in Path('/proc').iterdir():
        if not item.name.isdecimal() or int(item.name) in ancestors:continue
        try:
            argv=[a.decode(errors='replace') for a in (item/'cmdline').read_bytes().split(b'\0') if a]
            cmd=' '.join(argv)
            cwd=os.readlink(item/'cwd')
            # Inspect only explicitly named, non-secret runtime-path variables.
            runtime_paths=[]
            for env in (item/'environ').read_bytes().split(b'\0'):
                k,_,v=env.partition(b'=')
                if k in [b'HERMES_HOME',b'OPENCLAW_STATE_DIR',b'UV_CACHE_DIR']:runtime_paths.append(v.decode(errors='replace'))
            paths=[a for a in argv+runtime_paths if any(a==str(p) or a.startswith(str(p)+'/') for p in ROOTS)]
            hits=[str(p) for p in ROOTS if str(p) in cmd or cwd==str(p) or cwd.startswith(str(p)+'/') or any(a.startswith(str(p)+'/') for a in paths)]
            if hits:active.append(dict(pid=int(item.name),comm=(item/'comm').read_text().strip(),roots=hits,referenced_paths=paths,cwd=cwd))
        except OSError:continue
    return active

def package_records(venv):
    result=[]
    for site in list(venv.glob('lib/python*/site-packages'))+([venv/'Lib/site-packages'] if (venv/'Lib/site-packages').exists() else []):
        for info in site.glob('*.dist-info/METADATA'):
            # Only public installed-package headers, never environment/auth data.
            with info.open(errors='replace') as f:
                headers=[]
                for line in f:
                    if line in ['\n','\r\n']:break
                    if line.startswith(('Name: ','Version: ')):headers.append(line.strip())
            result.append(dict(metadata=str(info.relative_to(venv)),headers=headers))
    return result

def main():
    active=active_references()
    if active:write(R/'evidence/historical-cleanup-active-references.json',active)
    protected=[Path(x['path']).resolve() for x in json.loads((R/'evidence/source-architecture-index.json').read_text())['claims']]
    entries=json.loads((R/'evidence/full-storage-cleanup-candidates.json').read_text())['candidates']
    report=dict(at=time.time(),free_before_bytes=shutil.disk_usage(R).free,status='in_progress',removed=[],skipped=[],roots=[str(p) for p in ROOTS],preserved='Native logs, databases, configs, task inputs/outputs, result tables, authored source, PM facts and lock manifests. Current V6 baselines and all 41 cited source files remain untouched.',replay='These exact old generated dependency directories are released. Historical replay now requires native dependency reinstallation from retained versions/facts/locks. Offline whole-machine snapshot replay is not claimed.')
    report['active_references_retained']=active
    write(OUT,report)
    for entry in entries:
        path=Path(entry['path']);kind=entry['kind']
        if not path.exists():continue
        scope=str(path)
        for marker in ['/runtime-state/hermes/','/state/hermes/']:
            if marker in scope:scope=scope.split(marker)[0];break
        blockers=[p for p in active if any(a==scope or a.startswith(scope+'/') for a in p['referenced_paths']) or p['cwd']==scope or p['cwd'].startswith(scope+'/')]
        if blockers:
            report['skipped'].append(dict(path=str(path),reason='Actual same-profile process remains live',pids=[p['pid'] for p in blockers]));write(OUT,report);continue
        if path.is_symlink() or not any(path.resolve().is_relative_to(root.resolve()) for root in ROOTS):raise RuntimeError('Candidate escaped explicitly allowed historical roots')
        if any(p.is_relative_to(path.resolve()) for p in protected):raise RuntimeError('Candidate contains a cited authoritative source file')
        if kind=='generated_native_pm_environments':
            if path.name!='environments' or path.parent.parent.name!='installs' or not(path.parent/'facts.json').is_file():
                report['skipped'].append(dict(path=str(path),reason='Native install facts missing'));write(OUT,report);continue
            metadata=dict(facts_path=str(path.parent/'facts.json'),facts_sha256=hashlib.sha256((path.parent/'facts.json').read_bytes()).hexdigest(),generations=[])
            for generation in path.iterdir():
                if generation.is_dir():
                    for venv in [generation/'venv',generation]:
                        if(venv/'pyvenv.cfg').is_file():metadata['generations'].append(dict(path=str(venv.relative_to(path)),packages=package_records(venv)));break
        elif kind=='generated_python_environment':
            if not(path/'pyvenv.cfg').is_file():report['skipped'].append(dict(path=str(path),reason='No actual virtualenv marker'));write(OUT,report);continue
            metadata=dict(pyvenv_config_sha256=hashlib.sha256((path/'pyvenv.cfg').read_bytes()).hexdigest(),packages=package_records(path))
        elif kind=='regenerable_install_cache':
            if not(str(path).endswith('/cache/uv') or path.name=='_cacache'):raise RuntimeError('Not an approved package cache shape')
            metadata={}
        else:
            report['skipped'].append(dict(path=str(path),reason='Additional review required for this dependency kind'));write(OUT,report);continue
        size=subprocess.run(['du','-sx','-B1','--',str(path)],capture_output=True,text=True,check=True)
        allocated=int(size.stdout.split()[0])
        if allocated<1024**2:
            report['skipped'].append(dict(path=str(path),reason='Empty/small dependency placeholder retained'));write(OUT,report);continue
        row=dict(path=str(path),kind=kind,allocated_bytes_before=allocated,metadata=metadata,availability='pending_removal')
        report['removed'].append(row);write(OUT,report)
        shutil.rmtree(path)
        # Keep the directory mount point and identify why the binaries are gone.
        path.mkdir()
        write(path/'DEPENDENCIES_REBUILD_REQUIRED.json',dict(reason='Historical evaluation duplicate dependency cleanup after user-reported disk exhaustion',manifest=str(OUT),kind=kind,native_reinstall_required=True))
        row['availability']='native_reinstall_required'
        report['free_after_bytes']=shutil.disk_usage(R).free
        report['net_freed_bytes']=report['free_after_bytes']-report['free_before_bytes']
        write(OUT,report)
        print('RELEASED_HISTORICAL_DEPENDENCIES',len(report['removed']),allocated,'FREE',report['free_after_bytes'],flush=True)
    report.update(status='complete',finished_at=time.time(),free_after_bytes=shutil.disk_usage(R).free)
    report['net_freed_bytes']=report['free_after_bytes']-report['free_before_bytes'];write(OUT,report)
    print('HISTORICAL_CLEANUP_COMPLETE',len(report['removed']),report['net_freed_bytes'],report['free_after_bytes'],flush=True)

if __name__=='__main__':main()
