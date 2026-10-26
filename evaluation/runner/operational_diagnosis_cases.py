"""Frozen-runbook diagnosis and recovery using native records, then truth scoring."""
import errno
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time

import mechanism_cases as mechanism
import pilot
import service_path_cases as service

SCENARIOS={f'OBS-05-S{i:02}':name for i,name in enumerate([
    'invalid-configuration','state-corruption','extension-startup','storage-exhaustion'],1)}


def diagnose(native_records):
    """Input contains native output only, not the fault ID or intervention ledger."""
    rules=[('storage-exhaustion',r'ENOSPC|SQLITE_FULL|database or disk is full|no space left on device'),
        ('state-corruption',r'SQLITE_NOTADB|file is not a database|database disk image is malformed|malformed database'),
        ('extension-startup',r'EVAL_EXTENSION_STARTUP_FAILURE'),
        ('invalid-configuration',r'Invalid config|config invalid|invalid configuration|gateway\.port[^\n]{0,200}(?:number|string|invalid)')]
    found=[name for name,pattern in rules if re.search(pattern,native_records,re.I)]
    return dict(cause=found[0] if len(found)==1 else 'unknown',matched_categories=found,
        method='Frozen native-output rules; ambiguous or absent records remain unknown. Not a human operator study.')


def config_validation(root):
    env=dict(os.environ,OPENCLAW_STATE_DIR=str(root/'state'),OPENCLAW_CONFIG_PATH=str(root/'config.json'),
        OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_DISABLE_BUNDLED_PLUGINS='1')
    result=subprocess.run([pilot.NODE,pilot.CLI,'config','validate','--json'],capture_output=True,text=True,env=env,timeout=40)
    return dict(returncode=result.returncode,stdout=result.stdout[-6000:],stderr=result.stderr[-3000:])


def exhaust_owned_filesystem(root):
    directory=root/'owned-exhaustion';directory.mkdir();written=0;kernel_error=None
    try:
        for index in range(128):
            with (directory/str(index)).open('wb',buffering=0) as output:
                for _ in range(4):written+=output.write(b'e'*(256*1024))
    except OSError as error:
        kernel_error=error.errno
        if kernel_error!=errno.ENOSPC:raise
    if kernel_error!=errno.ENOSPC:raise RuntimeError('Declared owned-filesystem exhaustion boundary was not reached')
    return dict(bytes_written=written,kernel_errno=kernel_error,owned_directory=str(directory))


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];fixture=service.InstrumentedFixture();gateway=None;assertions=[]
    token='PILOT_OPERATIONS_'+scenario.replace('-','_')+'_U'+str(unit)
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    metadata={};recovery=[];backup=None;records=[]
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-diagnostic-records','independent-fault-ledger','recovery-receipts']))
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:mechanism.configure(p,'EXT-09-S01'));gateway.ready()
        fixture.register(token+'_CONTROL');positive=gateway.request(token+'_CONTROL')
        if not positive['accepted'] or fixture.receipts.get(token+'_CONTROL')!=1:raise RuntimeError('Native baseline positive control failed')
        row.update(native_invoked=True,fixture_validated=True)
        baseline=json.loads((root/'config.json').read_text());plugin=root/'composition-a/index.js';original=plugin.read_text()
        before=time.monotonic_ns();diagnostic_start=before
        if mode=='invalid-configuration':
            gateway.stop();bad=dict(baseline);bad['gateway']=dict(baseline['gateway'],port='INVALID_PORT');pilot.save(root/'config.json',bad)
            validation=config_validation(root);records.append(json.dumps(validation));metadata['config_validation']=validation
            gateway=pilot.Gateway(root,configurer=service.reuse)
            try:gateway.ready();metadata['faulted_startup_ready']=True
            except RuntimeError as error:records.append(str(error));metadata['faulted_startup_ready']=False
            records.extend(gateway.log_tail);gateway.stop()
        elif mode=='state-corruption':
            gateway.stop();candidates=[]
            for database in (root/'state').rglob('*.sqlite'):
                connection=sqlite3.connect(str(database));tables={v[0] for v in connection.execute("select name from sqlite_master where type='table'")};connection.close()
                if 'transcript_events' in tables:candidates.append(database)
            if len(candidates)!=1:raise RuntimeError('Cannot identify the native transcript store for corruption injection')
            database=candidates[0];backup=root/'owned-pre-fault.sqlite'
            if database.stat().st_size>4*1024**2:raise RuntimeError('Native synthetic store exceeds the bounded backup allowance')
            source=sqlite3.connect(str(database));target=sqlite3.connect(str(backup));source.backup(target);target.close();source.close()
            with database.open('r+b') as output:output.write(b'OWNED_INVALID_SQLITE_HEADER_00000')
            metadata['corrupted_owned_database']=str(database.relative_to(root))
            gateway=pilot.Gateway(root,configurer=service.reuse)
            try:gateway.ready();metadata['faulted_startup_ready']=True
            except RuntimeError as error:records.append(str(error));metadata['faulted_startup_ready']=False
            if metadata['faulted_startup_ready']:
                item=token+'_FAULTED';fixture.register(item);metadata['faulted_request']=gateway.request(item)
            records.extend(gateway.log_tail);gateway.stop()
        elif mode=='extension-startup':
            gateway.stop();plugin.write_text("throw new Error('EVAL_EXTENSION_STARTUP_FAILURE');\n")
            gateway=pilot.Gateway(root,configurer=service.reuse)
            try:gateway.ready();metadata['faulted_startup_ready']=True
            except RuntimeError as error:records.append(str(error));metadata['faulted_startup_ready']=False
            records.extend(gateway.log_tail)
            if metadata['faulted_startup_ready']:
                unaffected=token+'_UNAFFECTED';fixture.register(unaffected,tool='eval_other')
                metadata['unaffected_plugin_request']=gateway.request(unaffected)
            gateway.stop()
        else:
            metadata['independent_exhaustion']=exhaust_owned_filesystem(root)
            item=token+'_FULL';fixture.register(item);metadata['faulted_request']=gateway.request(item)
            time.sleep(.5);records.extend(gateway.log_tail)
            # Free only evaluator-owned filler before reading logs/restarting.
            shutil.rmtree(root/'owned-exhaustion')
            recovery.append(dict(action='remove-owned-exhaustion-files',privilege='run-owner'))
            gateway.stop()
        native_log=root/'gateway-native.log'
        if native_log.exists():records.append(native_log.read_text(errors='replace')[-24000:])
        native_text='\n'.join(records)
        diagnosed=diagnose(native_text)
        metadata.update(diagnosis=diagnosed,diagnostic_wall_ms=(time.monotonic_ns()-diagnostic_start)/1e6,
            native_diagnostic_excerpt=native_text[-16000:],native_diagnostic_bytes=len(native_text.encode()),
            truth_category=mode,runbook_version=1,diagnostic_actions=['native config validation (S01)','native startup/HTTP attempt','native stdout and structured file log inspection'],
            operator_model='Automated frozen runbook. Wall time includes process startup and waiting; human active minutes are unknown.',human_active_seconds=None)
        check('native-records-identify-injected-category',diagnosed['cause']==mode)
        # Recovery actions are fixed by the predeclared runbook. They are not
        # supplied to the diagnosis function and are scored independently.
        if mode=='invalid-configuration':
            pilot.save(root/'config.json',baseline);recovery.append(dict(action='restore-owned-valid-config',privilege='run-owner'))
        elif mode=='state-corruption':
            for suffix in ['-wal','-shm']:Path(str(database)+suffix).unlink(missing_ok=True)
            shutil.copyfile(backup,database);backup.unlink();recovery.append(dict(action='restore-bounded-pre-fault-native-database',privilege='run-owner'))
        elif mode=='extension-startup':
            plugin.write_text(original);recovery.append(dict(action='restore-owned-plugin-source',privilege='run-owner'))
        recovery.append(dict(action='restart-native-gateway',privilege='run-owner'))
        gateway=pilot.Gateway(root,configurer=service.reuse)
        restored=False;result=None
        try:
            gateway.ready();item=token+'_RESTORED';fixture.register(item);result=gateway.request(item)
            restored=result['accepted'] and fixture.receipts.get(item)==1
        except RuntimeError as error:metadata['recovery_native_error']=str(error)[:3000]
        check('recovery-validated-by-independent-effect',restored)
        metadata.update(recovery_actions=recovery,logical_recovery_interventions=len(recovery),recovery_request=result,
            total_wall_ms=(time.monotonic_ns()-before)/1e6,backup_scope='At most one owned synthetic native database, bounded to 4 MiB; no shared environment copy.')
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            metadata=metadata,independent_events=fixture.events,independent_receipts=fixture.receipts,
            resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2500],metadata=metadata)
    finally:
        if gateway:gateway.stop()
        fixture.close();shutil.rmtree(root,ignore_errors=True)
        row['owned_state_retained']=root.exists()
    return row
