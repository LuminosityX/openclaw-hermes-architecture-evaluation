"""Actual old/new schema migration faults and native snapshot rollback activation."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile
import time

import backup_cases
import migration_trace
import native_freeze
from operation_fixture import OperationFixture
import pilot
from portable_support import staged_asset,transcript_inventory
import privacy_cases
import service_path_cases as service
import version_skew_cases

SCENARIOS={f'REL-11-S{i:02}':mode for i,mode in enumerate(['before','during','after','extension'],1)}
OLD='/previous/node_modules/openclaw/openclaw.mjs'


def schemas(root):
    result=[]
    for path in (root/'state').rglob('*.sqlite'):
        db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=2)
        try:
            if db.execute("select 1 from sqlite_master where name='transcript_events' and type='table'").fetchone():
                result.append(dict(path=str(path),user_version=db.execute('pragma user_version').fetchone()[0],schema_cookie=db.execute('pragma schema_version').fetchone()[0],quick_check=[list(v) for v in db.execute('pragma quick_check')]))
        finally:db.close()
    if len(result)!=1:raise RuntimeError('Exactly one real native agent transcript database is required')
    return result[0]


def configure(root):return pilot.configuration(root,route='mcp',tool_search=False)


def native(root,*arguments,cli=None,timeout=100):
    def enter():(native_freeze.ROOT/'procs').write_text(str(os.getpid()))
    execution=subprocess.run(['/usr/bin/setpriv','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',pilot.NODE,cli or pilot.CLI,*map(str,arguments)],env=backup_cases.environment(root),capture_output=True,text=True,timeout=timeout,preexec_fn=enter,start_new_session=True)
    return dict(arguments=list(map(str,arguments)),core_cli=cli or pilot.CLI,returncode=execution.returncode,stdout=execution.stdout[-7000:],stderr=execution.stderr[-4000:])


def old_extension(root):
    plugin=root/'owned-old-extension';plugin.mkdir()
    pilot.save(plugin/'package.json',dict(name='eval-old-only',version='1.0.0',type='module',openclaw=dict(extensions=['./index.mjs'])))
    pilot.save(plugin/'openclaw.plugin.json',dict(id='eval-old-only',activation=dict(onStartup=True),contracts=dict(tools=['old_only_probe']),configSchema=dict(type='object',properties={},additionalProperties=False)))
    code="""import fs from 'node:fs';import path from 'node:path';
export default {id:'eval-old-only',register(api){
 let dir=path.dirname(process.argv[1]),version;
 for(let i=0;i<8;i++,dir=path.dirname(dir)){try{const p=JSON.parse(fs.readFileSync(path.join(dir,'package.json'),'utf8'));if(p.name==='openclaw'){version=p.version;break;}}catch{}}
 if(version!=='2026.10.4')throw new Error('OWNED_OLD_EXTENSION_INCOMPATIBLE_'+version);
 api.registerTool({name:'old_only_probe',description:'Version constrained owned extension',parameters:{type:'object',properties:{token:{type:'string'}},required:['token']},async execute(id,args){const r=await fetch('http://127.0.0.1:18080/effect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:args.token,pid:process.pid})});return {content:[{type:'text',text:JSON.stringify(await r.json())}]};}});
}};\n"""
    (plugin/'index.mjs').write_text(code)
    config=json.loads((root/'config.json').read_text());config['plugins']=dict(allow=['eval-old-only'],load=dict(paths=[str(plugin)]),entries={'eval-old-only':dict(enabled=True)})
    config['tools']['allow'].append('old_only_probe');pilot.save(root/'config.json',config)
    return hashlib.sha256(code.encode()).hexdigest()


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];fixture=OperationFixture();gateway=None;original=pilot.CLI;metadata={};assertions=[];requests=[];subject=root/'subject'
    token='PILOT_MIGRATION_'+scenario.replace('-','_')+'_U'+str(unit);session=token.lower()+'_retained'
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,value):assertions.append(dict(name=name,verdict='pass' if value else 'fail',evidence=['actual-old-and-current-native-cli','independent-read-only-sqlite-schema-and-transcript-inventory','kernel-observed-owned-WAL-fault-boundary','native-backup-restore-and-old-core-continuation']))
    def start(cli,configurer=service.reuse):
        nonlocal gateway
        pilot.CLI=cli;gateway=pilot.Gateway(subject,configurer=configurer,native_cgroup=True,drop_capabilities=True);gateway.ready(timeout=100)
    def stop():
        nonlocal gateway
        if gateway:gateway.stop();gateway=None
        native_freeze.kill()
    def capture():
        result=privacy_cases.wire(subject,[dict(method='chat.history',params=dict(sessionKey='agent:main:pilot:'+session,limit=100,maxBytes=262144))])
        if not all(v.get('result',{}).get('ok') for v in result['responses']):raise RuntimeError('Version-compatible native history positive control failed')
        return result
    def probe(suffix,tool='probe__eval_probe'):
        item=token+'_'+suffix;fixture.plan(item,tool,dict(token=item),'RECEIPT:'+item);result=gateway.request(item,session_key=session);requests.append(result);return result['accepted'] and fixture.receipts.get(item)==1
    try:
        identity=version_skew_cases.environment_selfcheck();expected=identity['target']
        if expected['version']!='2026.10.4' or expected['agent_schema_version']!=24:raise RuntimeError('Actual schema-migration source must be the explicitly pinned 24 source')
        start(OLD,configure)
        if not probe('ACKNOWLEDGED'):raise RuntimeError('Old native persisted transcript control failed')
        acknowledged=capture()
        stop();before=schemas(subject)
        if before['user_version']!=24:raise RuntimeError('Historical core did not produce actual schema 24')
        archive=root/'pre-upgrade.tar.gz'
        creation=native(subject,'backup','create','--output',archive,'--verify','--json',cli=OLD);native_freeze.kill()
        if creation['returncode'] or not archive.is_file():raise RuntimeError('Native old-core backup failed: '+json.dumps(creation)[-1500:])
        with tarfile.open(archive,'r:gz') as source:
            entries=[m for m in source.getmembers() if m.isfile() and m.name.endswith('/manifest.json') and '/payload/' not in m.name]
            if len(entries)!=1:raise RuntimeError('Native backup manifest is ambiguous')
            manifest=json.load(source.extractfile(entries[0]))
        # Establish the exact supported backup generation independently before
        # injecting a fault. Backup normalization is part of the native contract.
        stage=root/'baseline-staging';staged=native(subject,'backup','restore',archive,'--target',stage,'--json',cli=OLD);native_freeze.kill()
        if staged['returncode']:raise RuntimeError('Native snapshot baseline restore failed')
        snapshot=transcript_inventory(staged_asset(stage,manifest,'state'));shutil.rmtree(stage)
        metadata.update(historical_comparison_identity=identity,pre_upgrade_schema=before,pre_upgrade_acknowledgement=acknowledged,native_backup_creation=creation,native_backup_baseline_restore=staged,snapshot_transcript_inventory=snapshot,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
        if mode=='extension':
            metadata['exact_old_only_extension_sha256']=old_extension(subject);start(OLD)
            if not probe('OLD_EXTENSION_CONTROL','old_only_probe'):raise RuntimeError('Actual old-only extension did not work before upgrade')
            stop()
        pilot.CLI=original
        if mode in {'before','during'}:
            metadata['actual_migration_interruption']=migration_trace.interrupt(['/usr/bin/setpriv','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all',pilot.NODE,original,'doctor','--fix','--non-interactive'],backup_cases.environment(subject),Path(before['path']),before['schema_cookie'],25,'before' if mode=='before' else 'during',root/'traced-migration.log')
            at_cut=schemas(subject);metadata['committed_schema_after_fault']=at_cut
            if at_cut['user_version']!=24:raise RuntimeError('Observed WAL boundary was not before the migration transaction commit')
            row.update(native_invoked=True,fixture_validated=True)
            check('interrupted-native-migration-preserves-readable-committed-old-schema',at_cut['quick_check']==[['ok']])
            start(OLD);check('old-core-can-reopen-uncommitted-migration-state',probe('RECOVERED_BEFORE_SNAPSHOT'));stop()
        else:
            migration=native(subject,'doctor','--fix','--non-interactive');native_freeze.kill();metadata['actual_native_migration']=migration
            advanced=schemas(subject);metadata['committed_new_schema']=advanced
            if advanced['user_version']!=25:raise RuntimeError('Actual native Doctor did not advance schema 24 to 25: '+json.dumps(migration)[-1800:])
            row.update(native_invoked=True,fixture_validated=True)
            check('actual-new-schema-commits-without-integrity-loss',advanced['quick_check']==[['ok']])
            if mode=='after':
                pilot.CLI=original;gateway=pilot.Gateway(subject,configurer=service.reuse,native_cgroup=True,drop_capabilities=True)
                connection=http.client.HTTPConnection('127.0.0.1',18789,timeout=.3)
                try:
                    connection.request('GET','/readyz');response=connection.getresponse();ready=response.status==200;response.read()
                except OSError:ready=False
                finally:connection.close()
                if ready:raise RuntimeError('New service became ready before actual post-commit interruption')
                metadata['post_commit_pre_ready_fault']=dict(schema_version=25,observed_ready=False,actual_gateway_pid=gateway.process.pid)
                native_freeze.kill();gateway.process.wait(timeout=5);stop()
            else:
                start(original);check('unrelated-native-work-survives-incompatible-extension',probe('NEW_GENERIC_CONTROL'))
                check('version-constrained-extension-does-not-execute-on-new-core',not probe('NEW_INCOMPATIBLE','old_only_probe'))
                diagnostics=''.join(gateway.log_tail)+(subject/'gateway-native.log').read_text()[-30000:]
                if 'OWNED_OLD_EXTENSION_INCOMPATIBLE_' not in diagnostics:raise RuntimeError('Actual old-only registration incompatibility was not independently observed')
                metadata['native_incompatible_extension_diagnostic']=diagnostics[-5000:];stop()
                metadata['extension_scope']='Deliberately version-constrained owned extension verified on actual old core; no assertion that all real-world extensions break or that an upstream SDK symbol was removed.'
            refusal=native(subject,'doctor','--non-interactive',cli=OLD);native_freeze.kill();metadata['old_core_on_new_schema']=refusal
            diagnostic=(refusal['stdout']+refusal['stderr']).lower()
            check('unsupported-binary-downgrade-is-explicit-or-retains-readable-data',('newer' in diagnostic or 'schema' in diagnostic or 'version' in diagnostic) and schemas(subject)['quick_check']==[['ok']])
        # Documented rollback restores a native backup, then activates the old
        # binary. Entire assets are replaced; no SQLite row/schema edits occur.
        operator=root/'clean-restore-operator';configure(operator);restore=root/'rollback-staging'
        restored=native(operator,'backup','restore',archive,'--target',restore,'--json',cli=original);native_freeze.kill();metadata['native_snapshot_rollback']=restored
        if restored['returncode']:raise RuntimeError('Native staged rollback restore failed: '+json.dumps(restored)[-1500:])
        restored_state=staged_asset(restore,manifest,'state');inventory=transcript_inventory(restored_state)
        check('restored-native-backup-preserves-every-transcript-column-and-id',inventory==snapshot)
        for kind,destination in [('state',subject/'state'),('config',subject/'config.json'),('workspace',subject/'workspace')]:
            source=staged_asset(restore,manifest,kind)
            if destination.is_dir():shutil.rmtree(destination)
            elif destination.exists():destination.unlink()
            shutil.move(str(source),str(destination))
        start(OLD);check('actual-old-core-continues-after-native-snapshot-rollback',probe('AFTER_SNAPSHOT_ROLLBACK'))
        recovered=capture()
        check('acknowledged-pre-upgrade-user-message-remains-visible',token+'_ACKNOWLEDGED' in json.dumps(recovered))
        metadata.update(post_rollback_schema=schemas(subject),post_rollback_native_history=recovered,rollback_steps=['stop all owned native processes','native backup restore to clean staging using matching current CLI','activate entire native state/config/workspace assets at original paths','start pinned historical binary','continue original session with actual MCP effect'])
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,requests=requests,paid_model_calls=0,resources=gateway.sampler.summary())
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2600],metadata=metadata,requests=requests)
    finally:
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-5000:]
        native_freeze.kill();pilot.CLI=original;row.update(independent_effects=fixture.receipts,independent_events=fixture.events,native_tool_returns=fixture.tool_returns)
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
