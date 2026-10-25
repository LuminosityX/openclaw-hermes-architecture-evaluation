"""Capacity repair: remove only enumerated regenerable experiment dependencies.

Keep native state, logs, task inputs, results, source pins and one representative
archive per current dependency variant. The availability manifest supersedes old
archive restore instructions; deleted environments require native reinstallation.
"""
import hashlib
import json
import os
import shutil
import signal
import time
from pathlib import Path

R = Path('/root/output/oc-hermes-execution-20261024-v6')
OUT = R / 'evidence/disk-capacity-reclamation.json'


def main():
    for pid in [3214358, 3214292]:
        p = Path(f'/proc/{pid}/status')
        if p.exists() and '\nState:\tT' not in p.read_text():
            raise RuntimeError('Native queue must be paused before capacity repair')
    before = shutil.disk_usage(R).free
    targets = []
    for base in [R/'runs-install-rebuild', R/'runs-install-rebuild/state-restore']:
        for family in ['openclaw', 'hermes']:
            for unit in [1, 2, 3]:
                if base == R/'runs-install-rebuild' and unit == 1:
                    continue  # Keep a representative fresh-install dependency archive.
                case = base/f'u{unit}'/family
                if not json.loads((case/'result.json').read_text()).get('passed'):
                    raise RuntimeError('Unfinished install case')
                targets.append((case/'rebuilt-application-dependencies.tar.gz', case/'dependency-archive.json'))
    for parent in ['runs-protocols/anthropic', 'runs-extensions', 'runs-import-compat']:
        for unit in [2, 3]:
            case = R/parent/f'u{unit}'/'hermes'
            if not (case/'result.json').exists():
                raise RuntimeError('Incomplete native case')
            targets.append((case/'completed-private-dependency-environments.tar.gz', case/'dependency-archive.json'))
    upgrades = json.loads((R/'results/upgrades.json').read_text())
    if len(upgrades) != 6 or not all(x['passed'] for x in upgrades):
        raise RuntimeError('Old runtime still needed by incomplete upgrade cases')
    targets += [
        (R/'runtime/hermes-previous-tools-retained.tar.gz', R/'runtime/hermes-previous-tools-archive.json'),
        (R/'runtime/openclaw-previous-dependencies.tar.gz', R/'runtime/openclaw-previous-dependency-archive.json'),
    ]
    rows = []
    manifest = dict(at=time.time(),free_before_bytes=before,status='removing_enumerated_regenerable_dependencies',removed=rows,
        preserved='Native databases, configs, logs, raw measurements, task inputs/outputs, source code and source/version/lock manifests. Current subject runtimes and shared observability SDK runtime are unchanged.',
        replay_limitation='Removed dependency archives and obsolete installer environments require a native reinstall from retained pins/manifests; old archive restore instructions for these exact paths are superseded by this availability manifest.')
    def persist():
        OUT.write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    persist()
    for path, metadata in targets:
        if not path.exists():
            continue
        expected = json.loads(metadata.read_text()).get('sha256') if metadata.exists() else None
        with path.open('rb') as f:
            actual = hashlib.file_digest(f,'sha256').hexdigest()
        if expected and expected != actual:
            raise RuntimeError('Dependency archive no longer matches retained manifest: '+str(path))
        row = dict(path=str(path.relative_to(R)),bytes=path.stat().st_size,sha256=actual,metadata=str(metadata.relative_to(R)),kind='redundant_or_completed_old_release_dependency_archive')
        path.unlink()
        rows.append(row);persist()
        print('REMOVED_DEPENDENCY_COPY',row['path'],row['bytes'],flush=True)
    # Only task-private package caches and a completed OLD native installer.
    for path in [R/'runtime/npm-cache',R/'runtime/hermes-installer/cache/uv',R/'runtime/otlp-decoder-pip-cache',R/'runtime/hermes-previous-installer']:
        if not path.exists():
            continue
        if not path.resolve().is_relative_to((R/'runtime').resolve()):
            raise RuntimeError('Cache unexpectedly resolves outside experiment runtime')
        row = dict(path=str(path.relative_to(R)),kind='redownloadable_experiment_cache_or_obsolete_installer')
        shutil.rmtree(path)
        if path.name != 'hermes-previous-installer':
            path.mkdir(parents=True)
        rows.append(row);persist()
        print('REMOVED_TASK_CACHE',row['path'],flush=True)
    manifest.update(status='complete',free_after_bytes=shutil.disk_usage(R).free)
    manifest['net_freed_bytes'] = manifest['free_after_bytes']-before
    persist()
    print(json.dumps({k:manifest[k] for k in ['status','free_before_bytes','free_after_bytes','net_freed_bytes']}),flush=True)


if __name__ == '__main__':
    main()
