"""Actual native full backups with concurrent writes, queued work and interruption."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import tarfile
import threading
import time

import mechanism_cases as mechanism
import pilot
import service_path_cases as service
import trace_access_cases

SCENARIOS={f'REL-10-S{i:02}':name for i,name in enumerate(['idle','concurrent-writes','queued-work','interrupted-backup'],1)}


def queued_admission(probe,session):
    for response in probe.get('responses',[]):
        result=response.get('result',{});info=result.get('payload',{}).get('sessionInfo',{})
        if result.get('ok') is True and info.get('key')==session and info.get('status')=='queued' and info.get('hasActiveRun') is True:return True
    return False


def environment(root):
    return dict(os.environ,OPENCLAW_STATE_DIR=str(root/'state'),OPENCLAW_CONFIG_PATH=str(root/'config.json'),
        OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_DISABLE_BUNDLED_PLUGINS='1')


def native_backup(root,*arguments,timeout=90):
    started=time.monotonic_ns()
    execution=subprocess.run([pilot.NODE,pilot.CLI,'backup',*map(str,arguments)],env=environment(root),
        capture_output=True,text=True,timeout=timeout)
    return dict(arguments=list(map(str,arguments)),returncode=execution.returncode,stdout=execution.stdout[-7000:],
        stderr=execution.stderr[-3000:],started_monotonic_ns=started,ended_monotonic_ns=time.monotonic_ns())


def inspect_archive(archive,scratch,control):
    """Independent integrity/token check, bounded and only on the hosted tmpfs."""
    with tarfile.open(archive,'r:gz') as source:
        entries=source.getmembers()
        if sum(e.size for e in entries)>16*1024**2:raise RuntimeError('Synthetic archive exceeds the predeclared expanded inspection bound')
        manifests=[e for e in entries if e.isfile() and e.name.endswith('/manifest.json') and '/payload/' not in e.name]
        if len(manifests)!=1:raise RuntimeError('Native archive did not contain exactly one root manifest')
        manifest=json.load(source.extractfile(manifests[0]));databases=[]
        for entry in entries:
            if not entry.isfile() or not entry.name.endswith('.sqlite'):continue
            if entry.size>4*1024**2:raise RuntimeError('Owned canonical database exceeds the inspection bound')
            data=source.extractfile(entry).read()
            if not data.startswith(b'SQLite format 3\x00'):continue
            path=scratch/('inspect-'+str(len(databases))+'.sqlite');path.write_bytes(data)
            connection=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
            integrity=connection.execute('pragma quick_check').fetchall()
            tables={r[0] for r in connection.execute("select name from sqlite_master where type='table'")}
            seen=False
            if 'transcript_events' in tables:
                for values in connection.execute('select * from transcript_events limit 1000'):
                    if control in ' '.join(v for v in values if isinstance(v,str)):seen=True
            connection.close();path.unlink()
            databases.append(dict(archive_path=entry.name,bytes=entry.size,sha256=hashlib.sha256(data).hexdigest(),
                quick_check=integrity,acknowledged_control_seen=seen,transcript_store='transcript_events' in tables))
        return dict(manifest_schema_version=manifest.get('schemaVersion',manifest.get('version')),
            manifest_sha256=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),
            manifest_keys=sorted(manifest),sqlite_inventory=manifest.get('sqliteSnapshots'),databases=databases,
            archive_entries=len(entries),expanded_bytes=sum(e.size for e in entries),
            archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),archive_bytes=archive.stat().st_size)


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];fixture=service.InstrumentedFixture();fixture.gate_timeout_seconds=30
    gateway=None;assertions=[];metadata={};requests=[];writer_stop=threading.Event();writer=None
    token='PILOT_BACKUP_'+scenario.replace('-','_')+'_U'+str(unit)
    row=dict(scenario_id=scenario,unit=unit,fixture_validated=False,native_invoked=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-backup-commands','independent-sqlite-inspection','independent-events']))
    def configure(path):
        config=service.configure(path);config['agents']['defaults']['maxConcurrent']=1
        pilot.save(path/'config.json',config);return config
    def request(item):
        result=gateway.request(item);requests.append({k:v for k,v in result.items() if k!='response_excerpt'});return result
    try:
        gateway=pilot.Gateway(root,configurer=configure);gateway.ready()
        control=token+'_CONTROL';fixture.register(control)
        positive=request(control)
        if not positive['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Native pre-backup positive control failed')
        row.update(native_invoked=True,fixture_validated=True)
        output=root/'backup-output';output.mkdir();archive=output/'baseline.tar.gz'
        if mode=='concurrent-writes':
            def write_work():
                index=0
                while not writer_stop.is_set() and index<60:
                    item=token+'_WRITE'+str(index);fixture.register(item);request(item);index+=1
            writer=threading.Thread(target=write_work);writer.start()
            if not mechanism.wait_events(fixture,'effect-commit',[token+'_WRITE0'],seconds=12):raise RuntimeError('Concurrent native writer did not start')
            creation=native_backup(root,'create','--output',archive,'--verify','--json')
            writer_stop.set();writer.join(timeout=40)
            if writer.is_alive():raise RuntimeError('Concurrent writer failed to drain')
            metadata['writer_scope']='Actual independent native sessions commit transcript writes throughout native backup invocation, until its result returns; no raw live database copies are used.'
        elif mode=='queued-work':
            fixture.release.clear();slow=token+'_ACTIVE';fixture.register(slow,gate=True)
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                active=pool.submit(request,slow)
                if not mechanism.wait_events(fixture,'effect-start',[slow],seconds=12):raise RuntimeError('Native active slot did not reach the gate')
                pending=[]
                for index in range(3):
                    item=token+'_QUEUED'+str(index);fixture.register(item);pending.append(pool.submit(request,item))
                time.sleep(.4)
                metadata['queued_request_futures_pending_before_backup']=all(not f.done() for f in pending)
                session='agent:main:pilot:'+(token+'_QUEUED0').lower()
                admission=trace_access_cases.public_probe(root,session)
                metadata['queued_native_admission']=admission
                if not queued_admission(admission,session):
                    raise RuntimeError('Offered queued request has no native history/custody admission evidence')
                if any(e['kind']=='provider-request' and e.get('token','').startswith(token+'_QUEUED') for e in fixture.events):
                    raise RuntimeError('Declared queued work already reached the provider before backup')
                creation=native_backup(root,'create','--output',archive,'--verify','--json',timeout=20)
                fixture.release.set();active.result(timeout=40)
                for future in pending:future.result(timeout=40)
            check('native-backup-runs-while-request-class-is-queued',metadata['queued_request_futures_pending_before_backup'])
        else:creation=native_backup(root,'create','--output',archive,'--verify','--json')
        metadata['creation']=creation
        check('native-full-backup-creation-and-verification-succeed',creation['returncode']==0 and archive.is_file())
        if creation['returncode']==0 and archive.exists():
            inspection=inspect_archive(archive,output,control);metadata['independent_archive_inspection']=inspection
            check('canonical-sqlite-snapshots-are-independently-readable',bool(inspection['databases']) and all(d['quick_check']==[('ok',)] for d in inspection['databases']))
            check('acknowledged-pre-backup-transcript-is-retained',any(d['transcript_store'] and d['acknowledged_control_seen'] for d in inspection['databases']))
            if mode=='idle':
                restored=root/'restored-staging'
                result=native_backup(root,'restore',archive,'--target',restored,'--json');metadata['native_staged_restore']=result
                check('native-archive-restores-to-fresh-staging',result['returncode']==0 and restored.exists())
                metadata['activation_scope']='Native restore stages state only; activation at a different path belongs to REL-06 and is not inferred here.'
            if mode=='interrupted-backup':
                original_hash=inspection['archive_sha256']
                (root/'workspace/owned-publication-payload.bin').write_bytes(os.urandom(2*1024**2))
                interrupted=output/'interrupted.tar.gz'
                before_tmp={str(p) for p in (pilot.BASE/'tmp').rglob('*')}
                before_output={str(p) for p in output.rglob('*')}
                command=[pilot.NODE,pilot.CLI,'backup','create','--output',str(interrupted),'--verify','--json']
                child=subprocess.Popen(command,env=environment(root),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
                started=time.monotonic_ns();boundary=None
                try:
                    until=time.monotonic()+30
                    while time.monotonic()<until and child.poll() is None:
                        candidates=[p for p in (pilot.BASE/'tmp').rglob('*') if str(p) not in before_tmp and 'backup' in str(p).lower()]
                        candidates.extend(p for p in output.rglob('*') if str(p) not in before_output and p.name!='interrupted.tar.gz')
                        if candidates:
                            boundary=[str(p) for p in candidates[:12]]
                            os.killpg(child.pid,signal.SIGKILL);break
                        time.sleep(.001)
                    stdout,stderr=child.communicate(timeout=10)
                finally:
                    if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
                metadata['interrupted_native_backup']=dict(returncode=child.returncode,started_monotonic_ns=started,
                    stopped_monotonic_ns=time.monotonic_ns(),observed_work_paths=boundary,stdout=stdout[-3000:],stderr=stderr[-3000:])
                if not boundary or child.returncode!=-signal.SIGKILL:raise RuntimeError('Native backup finished before the actual staging/publication interruption boundary')
                verify=native_backup(root,'verify',archive,'--json');metadata['previous_generation_reverification']=verify
                check('previous-valid-backup-survives-interruption',hashlib.sha256(archive.read_bytes()).hexdigest()==original_hash and verify['returncode']==0)
                if interrupted.exists():
                    incomplete=native_backup(root,'verify',interrupted,'--json');metadata['interrupted_archive_verification']=incomplete
                    check('partial-publication-not-accepted-as-valid-backup',incomplete['returncode']!=0)
                metadata['remaining_partial_state']=service.owned_inventory(output)
        writer_stop.set();fixture.release.set()
        after=token+'_AFTER';fixture.register(after);result=request(after)
        check('live-service-continues-after-backup-experiment',result['accepted'] and fixture.receipts.get(after)==1)
        check('all-offered-work-accounted-for',all(r['accepted'] for r in requests) and all(fixture.receipts.get(r['token'])==1 for r in requests))
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            metadata=metadata,requests=requests,independent_events=fixture.events,independent_receipts=fixture.receipts,
            resources=gateway.sampler.summary(),paid_model_calls=0,
            consistency_contract='Config captured before databases; native per-database committed-state snapshots. No claim of one globally atomic snapshot across all sources.')
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:3000],metadata=metadata)
    finally:
        writer_stop.set();fixture.release.set()
        if writer:writer.join(timeout=40)
        if gateway:gateway.stop()
        fixture.close();shutil.rmtree(root,ignore_errors=True)
        row['owned_state_retained']=root.exists()
    return row
