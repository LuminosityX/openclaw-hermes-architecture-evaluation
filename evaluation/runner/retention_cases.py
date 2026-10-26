"""Native rotation, archive record fidelity, redaction and declared file roles."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import time

import backup_cases
from operation_fixture import OperationFixture
import pilot
import privacy_cases
import service_path_cases as service

SCENARIOS={f'OBS-04-S{i:02}':mode for i,mode in enumerate(['retention','archive-roundtrip','redaction','tamper'],1)}
ROTATION_BYTES=16384
OFFERED_EVENTS=320


def transcript_inventory(root):
    result=[]
    for path in sorted(root.rglob('*.sqlite')):
        if path.is_symlink() or path.stat().st_size>4*1024**2:continue
        db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=3)
        try:
            if not db.execute("select 1 from sqlite_master where type='table' and name='transcript_events'").fetchone():continue
            rows=db.execute('select * from transcript_events limit 1001').fetchall()
            if len(rows)>1000:raise RuntimeError('Synthetic transcript exceeded independent record bound')
            encoded=[json.dumps([{'bytes_hex':v.hex()} if isinstance(v,bytes) else v for v in row],sort_keys=True,separators=(',',':')) for row in rows]
            result.append(dict(path=str(path.relative_to(root)),row_count=len(rows),
                ordered_independent_record_sha256=hashlib.sha256('\n'.join(sorted(encoded)).encode()).hexdigest(),
                integrity=db.execute('pragma quick_check').fetchall()))
        finally:db.close()
    return result


def configure(root,mode,token,canary):
    config=privacy_cases.configure(root,'redaction',canary) if mode=='redaction' else service.configure(root)
    config['logging']['level']='info'
    if mode=='retention':config['logging']['maxFileBytes']=ROTATION_BYTES
    # Parent access is an explicit run-owner filesystem boundary, recorded below.
    root.chmod(0o700)
    plugin=root/'composition-a/index.js';source=plugin.read_text()
    count=OFFERED_EVENTS if mode=='retention' else 1
    source=source.replace("  await announce('entered');", "  await announce('entered');\n  for(let i=0;i<(args.token==="+json.dumps(token)+"?"+str(count)+":1);i++)api.logger.info('RETENTION_EVENT_'+args.token+'_N'+String(i).padStart(5,'0')+' '+ 'x'.repeat(768));")
    plugin.write_text(source);pilot.save(root/'config.json',config);return config


def denied_file_edit(path):
    def change_identity():os.setgroups([]);os.setgid(65534);os.setuid(65534)
    script="import pathlib,sys\np=pathlib.Path(sys.argv[1])\ntry:\n p.open('ab').write(b'UNPRIVILEGED_FORGERY')\nexcept PermissionError:\n sys.exit(13)\n"
    result=subprocess.run(['/usr/bin/python3','-I','-c',script,str(path)],capture_output=True,text=True,timeout=5,preexec_fn=change_identity)
    return dict(uid=65534,gid=65534,returncode=result.returncode,stderr=result.stderr[-500:],permission_denied=result.returncode==13)


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];token='PILOT_RETENTION_'+scenario.replace('-','_')+'_U'+str(unit)
    canary='SYNTHETIC_SECRET_'+hashlib.sha256(token.encode()).hexdigest()[:40].upper()
    fixture=OperationFixture();gateway=None;assertions=[];metadata={};exports=[];requests=[]
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-records-and-public-export','independent-record-digests','owned-filesystem-role-probes','independent-effect-ledger']))
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:configure(p,mode,token,canary));gateway.ready()
        control=token+'_CONTROL';fixture.register(control)
        positive=gateway.request(control);requests.append(positive)
        if not positive['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Native retention baseline control failed')
        row.update(native_invoked=True,fixture_validated=True)
        session='agent:main:pilot:'+token.lower()
        if mode=='redaction':fixture.plan(token,'read',dict(path=str(root/'workspace/private-memory.txt')),canary)
        else:fixture.register(token)
        result=gateway.request(token);requests.append(result)
        exported=privacy_cases.history(root,session);exports.append(exported)
        check('actual-native-task-and-owner-record-access',result['accepted'] and exported['responses'][0]['result'].get('ok') is True)
        if mode=='retention':
            # Wait for native asynchronous file publication, bounded by the newest marker.
            marker='RETENTION_EVENT_'+token+'_N';deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                files=sorted(root.glob('gateway-native*.log'))
                if any(marker+'00319' in p.read_text(errors='replace') for p in files):break
                time.sleep(.1)
            files=sorted(root.glob('gateway-native*.log'));text='\n'.join(p.read_text(errors='replace') for p in files)
            indices=sorted(set(int(i) for i in re.findall(re.escape(marker)+r'(\d{5})',text)))
            metadata.update(offered_unique_events=OFFERED_EVENTS,retained_indices=indices,
                files=[dict(name=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files],
                declared_file_limit=ROTATION_BYTES,native_rotation_generations=5,
                scope='Native bounded JSONL file rotation, not a durable audit log. Older generations may be pruned. No synthetic queue overflow is offered (320 events < 4096 queue entries).')
            check('actual-retention-boundary-crossed',len(files)>1 and bool(indices) and 0 not in indices)
            check('newest-offered-record-retained',OFFERED_EVENTS-1 in indices)
            check('native-file-generation-and-byte-limits',len(files)<=6 and all(p.stat().st_size<=ROTATION_BYTES for p in files))
            deleted=privacy_cases.wire(root,[dict(method='sessions.delete',params=dict(key=session,deleteTranscript=True))]);exports.append(deleted)
            check('explicit-owner-transcript-prune-succeeds',deleted['responses'][0]['result'].get('ok') is True)
        elif mode=='archive-roundtrip':
            gateway.stop();before=transcript_inventory(root/'state')
            if len(before)!=1 or before[0]['row_count']==0:raise RuntimeError('Native source transcript identity positive control is absent')
            output=root/'owned-record-archive';output.mkdir();archive=output/'records.tar.gz'
            created=backup_cases.native_backup(root,'create','--output',archive,'--verify','--json');metadata['native_export']=created
            check('native-archive-export-verifies',created['returncode']==0 and archive.is_file())
            if created['returncode']==0 and archive.is_file():
                inspection=backup_cases.inspect_archive(archive,output,token);metadata['archive_inspection']=inspection
                restored=root/'owned-import';imported=backup_cases.native_backup(root,'restore',archive,'--target',restored,'--json');metadata['native_import']=imported
                after=transcript_inventory(restored) if restored.exists() else []
                metadata.update(source_record_inventory=before,restored_record_inventory=after)
                check('native-archive-restores-records',imported['returncode']==0 and bool(after))
                check('all-transcript-rows-and-identities-roundtrip',len(after)==1 and all(after[0][k]==before[0][k] for k in ['row_count','ordered_independent_record_sha256']) and after[0]['integrity']==[('ok',)])
            metadata['roundtrip_scope']='Native full-backup export, verify and restore into fresh staging; every bounded transcript_events row is independently compared, including original identities and payload columns. This does not claim the public chat.history JSON is accepted as a session-import format or prove activation at another path.'
        elif mode=='redaction':
            native=(root/'gateway-native.log').read_text(errors='replace')
            logs=privacy_cases.wire(root,[dict(method='logs.tail',params=dict(limit=200,maxBytes=262144))]);exports.append(logs)
            check('synthetic-secret-actually-reached-native-model-context',canary in json.dumps(fixture.tool_returns.get(token,[])))
            check('redaction-control-actually-logged','PRIVACY_LOG_CONTROL' in native)
            check('exact-configured-secret-absent-from-file-and-public-exports',canary not in native and canary not in json.dumps(exports))
            metadata['redaction_scope']='Exact full configured synthetic pattern in file, logs.tail and chat.history. Masked fragments, unconfigured sensitive formats, encoded attachments and model provider privacy are separate questions.'
        else:
            native=root/'gateway-native.log';denied=denied_file_edit(native);metadata['unprivileged_file_mutation']=denied
            check('unprivileged-os-identity-cannot-edit-owner-records',denied['permission_denied'])
            no_scope=privacy_cases.wire(root,[dict(method='logs.tail',params=dict(limit=100,maxBytes=262144))],role='none');exports.append(no_scope)
            response=no_scope['responses'][0]['result'];check('unscoped-device-cannot-export-owner-logs',response.get('ok') is False and response.get('error',{}).get('code')=='FORBIDDEN')
            gateway.stop();original=native.read_bytes();lines=original.decode().splitlines()
            base=next(json.loads(line) for line in reversed(lines) if line.startswith('{'))
            marker='OWNER_MODIFIED_RECORD_'+token;base['0']=marker;base['message']=marker
            with native.open('a') as target:target.write(json.dumps(base)+'\n')
            modified=native.read_bytes();metadata.update(owner_mutation_success=marker.encode() in modified,
                before_sha256=hashlib.sha256(original).hexdigest(),after_sha256=hashlib.sha256(modified).hexdigest(),
                log_mode=oct(stat.S_IMODE(native.stat().st_mode)),parent_mode=oct(stat.S_IMODE(root.stat().st_mode)),
                filesystem_owner_uid=os.geteuid(),native_record_signed_integrity_promised=False,
                scope='The run owner can edit ordinary local diagnostic files. This is recorded as a boundary, not a violation of a nonexistent append-only/signature promise. The actual UID 65534 and zero-scope device probes distinguish unprivileged roles from the owner.')
            check('owner-modification-boundary-observed',metadata['owner_mutation_success'] and original!=modified)
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            metadata=metadata,native_exports=exports,requests=requests,independent_events=fixture.events,
            independent_receipts=fixture.receipts,resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2200],metadata=metadata)
    finally:
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-3000:]
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
