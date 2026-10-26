#!/usr/bin/env python3
"""Install one official addon with native provenance on the disposable host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys

from suite import ROOT,require


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-modules',type=Path,required=True)
    parser.add_argument('--node',type=Path,required=True)
    parser.add_argument('--metadata',type=Path,required=True)
    args=parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.geteuid()==0,'Native addon setup is restricted to the disposable hosted controller')
    runtime=args.runtime_modules.resolve().parent;profile=runtime/'official-addon-profile'
    sys.path.insert(0,str(ROOT/'evaluation/runner'))
    import pilot
    profile.mkdir();pilot.configuration(profile)
    for name in ['home','cache']:(profile/name).mkdir()
    env=dict(os.environ,HOME=str(profile/'home'),XDG_CACHE_HOME=str(profile/'cache'),
        OPENCLAW_STATE_DIR=str(profile/'state'),OPENCLAW_CONFIG_PATH=str(profile/'config.json'),
        OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_DISABLE_BUNDLED_PLUGINS='1')
    env.pop('DEEPSEEK_API_KEY',None)
    cli=args.runtime_modules/'openclaw/openclaw.mjs'
    command=[str(args.node),str(cli),'plugins','install','@openclaw/diagnostics-otel@2026.10.7','--accept-capabilities']
    installed=subprocess.run(command,env=env,capture_output=True,text=True,timeout=300)
    args.metadata.mkdir(parents=True,exist_ok=True)
    diagnostic=dict(native_install_returncode=installed.returncode,native_install_stdout=installed.stdout[-12000:],native_install_stderr=installed.stderr[-6000:])
    (args.metadata/'observability-addon-setup.json').write_text(json.dumps(diagnostic)+'\n')
    require(installed.returncode==0,'Native official-addon installation failed: '+installed.stderr[-1800:])
    exported=subprocess.run([str(args.node),str(cli),'plugins','inspect','diagnostics-otel','--json'],env=env,capture_output=True,text=True,timeout=60)
    try:inspection=json.loads(exported.stdout) if exported.returncode==0 else None
    except ValueError:inspection=None
    require(isinstance(inspection,dict) and isinstance(inspection.get('install'),dict),'Native inspection did not export its authoritative install record')
    record=inspection['install'];records={'diagnostics-otel':record};package_root=Path(record['installPath']).resolve()
    require(package_root.is_relative_to(runtime) and package_root.is_dir(),'Native addon escaped its owned hosted prefix')
    package=json.loads((package_root/'package.json').read_text())
    require(package['name']=='@openclaw/diagnostics-otel' and package['version']=='2026.10.7','Native addon differs from its exact campaign version')
    require(record.get('integrity') and record.get('source') in {'npm','clawhub'},'Native addon did not retain registry provenance')
    project=package_root
    for parent in [package_root,*package_root.parents]:
        if not parent.is_relative_to(runtime):break
        if (parent/'package-lock.json').is_file() and (parent/'node_modules').is_dir():project=parent;break
    database=profile/'state/state/openclaw.sqlite';snapshot=runtime/'official-addon-state.sqlite'
    require(database.is_file(),'Native official-addon machine-state database was not created')
    source=sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True);target=sqlite3.connect(str(snapshot));source.backup(target);target.close();source.close()
    require(snapshot.stat().st_size<=4*1024**2,'Owned native installer database exceeds its 4 MiB snapshot bound')
    native_config=json.loads((profile/'config.json').read_text())
    template=dict(kind='native-official-addon-install-template',installs=records,package_root=str(package_root),project_root=str(project),
        entry_configuration=native_config.get('plugins',{}).get('entries',{}).get('diagnostics-otel',dict(enabled=True)),
        native_state_snapshot_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),native_state_snapshot_bytes=snapshot.stat().st_size,
        package_sha256=hashlib.sha256((package_root/'package.json').read_bytes()).hexdigest(),
        native_install_command=['openclaw','plugins','install','@openclaw/diagnostics-otel@2026.10.7','--accept-capabilities'],
        preparation_controller_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='One WAL-aware snapshot of the native installer machine-state database (at most 4 MiB), its unmodified registry provenance and one read-only addon dependency prefix. Retired plugins.installs config is not authored. No trust flags are fabricated; no whole runtime is copied.')
    (runtime/'official-addon-template.json').write_text(json.dumps(template)+'\n')
    (args.metadata/'observability-addon.json').write_text(json.dumps(template)+'\n')
    lock=project/'package-lock.json'
    if lock.is_file():
        require(lock.stat().st_size<=1024**2,'Addon dependency lock exceeds its hosted metadata bound')
        (args.metadata/'observability-addon-lock.json').write_bytes(lock.read_bytes())
    print(json.dumps(dict(addon=package['name'],version=package['version'],native_install_source=record['source'],owned_project=str(project))))


if __name__=='__main__':main()
