#!/usr/bin/env python3
"""Join actual Linux source execution with actual native Windows target execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time

from adapter_readiness import SOURCES,require_execution_ready
from campaign import load_plan,records_from,DEFAULT_PLAN
from run_campaign_family import bind_unit
from suite import ROOT,require
from target import verify_installation
sys.path.insert(0,str(ROOT/'evaluation/runner'))
from portable_core import PortableFixture,PortableGateway,configure,save
from portable_support import HostBounds,owned_child_environment,process_identity,staged_asset,transcript_inventory


def hashes():return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES['REL-08']}


def assertion(name,condition):return dict(name=name,verdict='pass' if condition else 'fail',evidence=['actual-native-Linux-and-Windows-execution','independent-file-process-and-transcript-artifacts'])


def archive_manifest(path):
    with tarfile.open(path,'r:gz') as source:
        entries=source.getmembers();require(sum(v.size for v in entries)<=16*1024**2,'Native source archive exceeds its expanded bound')
        matches=[v for v in entries if v.isfile() and v.name.endswith('/manifest.json') and '/payload/' not in v.name]
        require(len(matches)==1,'Native source archive has no unique root manifest')
        return json.load(source.extractfile(matches[0]))


def archive_inventory(path,inspection):
    inspection.mkdir()
    try:
        with tarfile.open(path,'r:gz') as source:
            index=0
            for member in source.getmembers():
                if not member.isfile() or not member.name.endswith('.sqlite'):continue
                require(member.size<=8*1024**2,'Source SQLite snapshot exceeds inspection bound')
                data=source.extractfile(member).read()
                if not data.startswith(b'SQLite format 3\x00'):continue
                target=inspection/str(index)/Path(member.name).name;target.parent.mkdir();target.write_bytes(data);index+=1
        return transcript_inventory(inspection)
    finally:shutil.rmtree(inspection)


def message_ids(history):
    return sorted({message.get('__openclaw',{}).get('id') for message in history.get('messages',[]) if message.get('__openclaw',{}).get('id')})


def native_texts(value,depth=0):
    if depth>8:return []
    if isinstance(value,str):
        try:parsed=json.loads(value)
        except ValueError:return [value]
        return [value,*native_texts(parsed,depth+1)] if parsed!=value else [value]
    if isinstance(value,list):return [text for child in value for text in native_texts(child,depth+1)]
    if isinstance(value,dict):return [text for child in value.values() for text in native_texts(child,depth+1)]
    return []


def run_local_semantics(root,node,modules,unit):
    fixture=PortableFixture();gateway=None;cases={};requests=[];prefix='PILOT_CROSS_OS_U'+str(unit);session='agent:main:crossos:u'+str(unit)
    def perform(suffix,tool,arguments,expected=''):
        token=prefix+'_'+suffix;fixture.plan(token,tool,arguments,expected);result=gateway.request(token,session);requests.append(dict(token=token,**result));return token,result
    try:
        gateway=PortableGateway(root,node,modules);gateway.ready()
        ready=None
        for attempt in range(4):
            token,ready=perform('READY_'+str(attempt),'read',dict(path=str(root/'workspace/public-ready.txt')),'OWNED_PORTABLE_READY')
            if ready['accepted']:break
            # Only the explicit, idempotent owned readiness read is retried.
            time.sleep(.5)
        require(ready and ready['accepted'],'Actual native '+os.name+' read positive control failed: '+json.dumps(ready)+' '+''.join(gateway.tail)[-1500:])
        full=gateway.rpc('sessions.patch',dict(key=session,permissionMode='full'))
        text='OWNED_CROSS_OS_U'+str(unit)+'_π_中文_🙂\n';relative='unicode space/π_中文_é_🙂.txt';path=root/'workspace'/relative
        perform('UNICODE_WRITE','write',dict(path=str(path),content=text))
        token,result=perform('UNICODE_READ','read',dict(path=str(path)),text.strip())
        checks=[assertion('native-Unicode-and-space-path-artifact-preserves-UTF8-bytes',path.is_file() and path.read_bytes()==text.encode()),assertion('native-read-returns-the-real-Unicode-artifact',result['accepted'])]
        upper=root/'workspace/CaseProbe.txt';lower=root/'workspace/caseprobe.txt'
        perform('UPPER_WRITE','write',dict(path=str(upper),content='UPPER_CASE_ARTIFACT'))
        perform('LOWER_WRITE','write',dict(path=str(lower),content='lower_case_artifact'))
        checks.append(assertion('case-distinct-source-artifacts-remain-independent',upper.is_file() and lower.is_file() and upper.read_text(encoding='utf8')=='UPPER_CASE_ARTIFACT' and lower.read_text(encoding='utf8')=='lower_case_artifact'))
        cases['REL-08-S01']=dict(assertions=checks,native_unicode_path=relative,native_artifact_sha256=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
            case_pair_artifact_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None for p in [upper,lower]},
            case_scope='Actual filesystem case distinction is tested, not assumed portable or classified as a security defect.')
        script=root/'workspace/owned-process.py';heartbeat=root/'workspace/heartbeat';pidfile=root/'workspace/worker-pid'
        script.write_text('import os,sys,time\nfrom pathlib import Path\np=Path(sys.argv[1]);p.write_text(str(os.getpid()))\nh=Path(sys.argv[2])\n'
            'if "--once" in sys.argv:print("OWNED_PROCESS_CONTROL");sys.exit(0)\n'
            'for i in range(180):\n with h.open("a") as f:f.write(str(i)+"\\n")\n time.sleep(.1)\n',encoding='utf8')
        def command(once=False):
            args=[sys.executable,str(script),str(pidfile),str(heartbeat),*(['--once'] if once else [])]
            return '& '+' '.join("'"+v.replace("'","''")+"'" for v in args) if os.name=='nt' else shlex.join(args)
        shell=[shutil.which('pwsh') or 'powershell','-NoProfile','-NonInteractive','-Command'] if os.name=='nt' else ['/bin/sh','-c']
        direct=subprocess.run([*shell,command(True)],env=gateway.env,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=15)
        require(direct.returncode==0 and 'OWNED_PROCESS_CONTROL' in direct.stdout,'Independent actual native shell/Python fixture positive control failed: '+direct.stderr[-1000:])
        pidfile.unlink(missing_ok=True);token,started=perform('START_PROCESS','exec',dict(command=command(),yieldMs=1000,timeoutSeconds=20))
        deadline=time.monotonic()+8
        while time.monotonic()<deadline and (not pidfile.is_file() or not heartbeat.is_file() or heartbeat.stat().st_size<4):time.sleep(.05)
        process_checks=[];identity=None;native_process_id=None
        if pidfile.is_file() and heartbeat.is_file():
            pid=int(pidfile.read_text());identity=process_identity(pid)
            token,listed=perform('LIST_PROCESS','process',dict(action='list'))
            text_return='\n'.join(native_texts(fixture.returns.get(token,[])))
            # The fresh native registry contains our one controlled exec only.
            # PowerShell's native display name may contain just '& python.exe'
            # and omit the script after truncation; it is not the handle.
            matches=sorted(set(re.findall(r'(?m)^\s*([^\s]+)\s+running\s+[^\n]*::',text_return)))
            if len(matches)==1:
                native_process_id=matches[0];perform('KILL_PROCESS','process',dict(action='kill',sessionId=native_process_id))
                deadline=time.monotonic()+2
                while time.monotonic()<deadline and process_identity(pid)==identity:time.sleep(.05)
                exited=process_identity(pid)!=identity;before=heartbeat.stat().st_size;time.sleep(.3)
                process_checks.extend([assertion('native-process-tool-terminates-the-actual-owned-descendant',bool(identity) and exited),assertion('actual-heartbeat-stops-after-native-cancellation',before==heartbeat.stat().st_size)])
            else:process_checks.append(assertion('native-process-list-exposes-its-real-running-handle',False))
            # Independent cleanup follows scoring and is never called native Stop.
            if identity and process_identity(pid)==identity:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(pid),'/T','/F'],capture_output=True,timeout=10)
                else:os.kill(pid,9)
        else:process_checks.append(assertion('native-exec-starts-the-independently-verified-command',False))
        cases['REL-08-S02']=dict(assertions=process_checks,native_process_id=native_process_id,independent_process_identity=identity,
            direct_shell_positive_control=dict(returncode=direct.returncode,stdout=direct.stdout[-500:]),native_exec_result=started)
        history=gateway.history(session)
        require(history.get('sessionId') and message_ids(history),'Actual native source/target history has no stable session/message identity')
        result=dict(cases=cases,session_key=session,session_id=history['sessionId'],message_ids=message_ids(history),native_history=history,
            native_permission_result=full,requests=requests,native_tool_returns=fixture.returns,native_tool_schemas=fixture.native_tool_schemas,provider_events=fixture.events,config=gateway.config,environment_os=os.name)
        gateway.stop();gateway=None
        return result
    finally:
        if gateway:gateway.stop()
        fixture.close()


def native_command(root,node,modules,*arguments,env=None,timeout=90):
    result=subprocess.run([str(node),str(modules/'openclaw/openclaw.mjs'),*map(str,arguments)],env=env or owned_child_environment(root),capture_output=True,text=True,encoding='utf8',errors='replace',timeout=timeout)
    return dict(arguments=list(map(str,arguments)),returncode=result.returncode,stdout=result.stdout[:32000],stderr=result.stderr[-3000:])


def source_unit(root,node,modules,unit,output):
    result=run_local_semantics(root,node,modules,unit);archive=output/('source-'+str(unit)+'.tar.gz')
    collision=output/('case-collision-'+str(unit)+'.tar.gz')
    collision_probe=native_command(root,node,modules,'backup','create','--output',collision,'--verify','--json')
    result['cases']['REL-08-S01']['native_collision_backup_probe']=collision_probe
    collision_rejected=collision_probe['returncode']!=0 and 'portable path collision' in collision_probe['stdout']+collision_probe['stderr']
    result['cases']['REL-08-S01']['assertions'].append(assertion('native-Linux-backup-does-not-silently-export-case-colliding-artifacts',collision_rejected))
    # The file-semantics and import scenarios are distinct. Preserve the real
    # collision probe, then remove only those two owned probe files so state
    # import receives a genuinely verified portable source archive.
    for name in ['CaseProbe.txt','caseprobe.txt']:(root/'workspace'/name).unlink(missing_ok=True)
    created=native_command(root,node,modules,'backup','create','--output',archive,'--verify','--json')
    require(created['returncode']==0 and archive.is_file(),'Actual Linux native backup positive control failed: '+json.dumps(created)[-2000:])
    manifest=archive_manifest(archive);inventory=archive_inventory(archive,root/'independent-archive-inspection')
    require(inventory and any(v['row_count'] for v in inventory),'Actual Linux backup contains no independently readable native transcript rows')
    result.update(source_os='Linux',unit=unit,run_id=os.environ['GITHUB_RUN_ID'],controller_commit=os.environ['GITHUB_SHA'],controller_sha256=hashes(),
        source_archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),native_archive_manifest=manifest,archive_transcript_inventory=inventory,native_backup=created,
        original_state=str(root/'state'),original_agent=str(root/'state/agents/main/agent'),full_campaign_coverage=False)
    return result


def target_unit(root,node,modules,unit,source,archive):
    require(source['source_os']=='Linux' and source['unit']==unit and source['run_id']==os.environ['GITHUB_RUN_ID'] and source['controller_commit']==os.environ['GITHUB_SHA'],'Actual source host/unit provenance mismatch')
    require(source['controller_sha256']==hashes() and hashlib.sha256(archive.read_bytes()).hexdigest()==source['source_archive_sha256'],'Cross-host native evidence/source digest mismatch')
    local=run_local_semantics(root,node,modules,unit);rows=[]
    for sid in ['REL-08-S01','REL-08-S02']:
        checks=[*source['cases'][sid]['assertions'],*local['cases'][sid]['assertions']]
        rows.append(dict(scenario_id=sid,unit=unit,state='pass' if all(a['verdict']=='pass' for a in checks) else 'fail',native_invoked=True,fixture_validated=True,assertions=checks,linux_control=source['cases'][sid],windows_target=local['cases'][sid]))
    restored=root/'native-restored';restore=native_command(root,node,modules,'backup','restore',archive,'--target',restored,'--json')
    checks=[assertion('actual-Windows-native-restore-accepts-the-verified-Linux-archive',restore['returncode']==0)]
    imported_inventory=transcript_inventory(restored) if restored.exists() else []
    checks.append(assertion('native-staged-import-preserves-all-archived-transcript-columns-and-record-identities',imported_inventory==source['archive_transcript_inventory']))
    rows.append(dict(scenario_id='REL-08-S03',unit=unit,state='pass' if all(a['verdict']=='pass' for a in checks) else 'fail',native_invoked=True,fixture_validated=True,assertions=checks,
        native_restore=restore,linux_archive_inventory=source['archive_transcript_inventory'],windows_staged_inventory=imported_inventory))
    continuation=[];fixture=None;gateway=None;metadata=dict(native_restore_returncode=restore['returncode'])
    if restore['returncode']==0:
        fixture=PortableFixture();manifest=source['native_archive_manifest'];state=staged_asset(restored,manifest,'state');workspace=staged_asset(restored,manifest,'workspace')
        config=json.loads(json.dumps(source['config']));config['agents']['defaults']['workspace']=str(workspace)
        relative_agent=Path(source['original_agent']).as_posix().removeprefix(Path(source['original_state']).as_posix().rstrip('/')+'/')
        require(relative_agent!=source['original_agent'] and '..' not in Path(relative_agent).parts,'Declared source agent does not belong to the backed-up state asset')
        config['agents']['entries']['main'].update(workspace=str(workspace),agentDir=str(state.joinpath(*relative_agent.split('/'))));config['logging']['file']=str(root/'activated-native.log')
        save(root/'config.json',config);env=owned_child_environment(root);env['OPENCLAW_STATE_DIR']=str(state)
        metadata['documented_operator_mapping']=dict(state=str(state),workspace=str(workspace),agentDir=config['agents']['entries']['main']['agentDir'],database_rows_manually_changed=False)
        metadata['native_doctor']=native_command(root,node,modules,'doctor','--fix','--non-interactive',env=env,timeout=90)
        activated_at=time.monotonic_ns();metadata['activation_ready_deadline_seconds']=120
        try:
            gateway=PortableGateway(root,node,modules,config=config,state=state);gateway.ready(timeout=120);before=gateway.history(source['session_key'])
            token='PILOT_CROSS_OS_CONTINUE_U'+str(unit);fixture.plan(token,'read',dict(path=str(workspace/'public-ready.txt')),'OWNED_PORTABLE_READY')
            actual=gateway.request(token,source['session_key']);after=gateway.history(source['session_key'])
            continuation.extend([assertion('actual-Windows-activation-keeps-the-original-native-session-id',before.get('sessionId')==source['session_id'] and after.get('sessionId')==source['session_id']),
                assertion('original-native-message-identities-survive-and-new-work-continues',set(source['message_ids'])<=set(message_ids(after)) and actual['accepted'])])
            metadata.update(native_history_before=before,native_continuation=actual,native_history_after=after)
        except RuntimeError as error:
            if gateway and gateway.guard_failure:raise RuntimeError('Owned cross-OS fixture guard invalidated activation: '+gateway.guard_failure)
            continuation.append(assertion('actual-Windows-native-activation-and-continuation-succeed',False));metadata['actual_native_activation_error']=str(error)[:2200]
        finally:
            metadata['activation_observation_ms']=(time.monotonic_ns()-activated_at)/1e6
            if gateway:gateway.stop();metadata['native_gateway_tail']=''.join(gateway.tail)[-2500:]
            fixture.close()
    else:continuation.append(assertion('native-continuation-can-activate-the-source-state',False))
    rows.append(dict(scenario_id='REL-08-S04',unit=unit,state='pass' if all(a['verdict']=='pass' for a in continuation) else 'fail',native_invoked=True,fixture_validated=True,assertions=continuation,metadata=metadata))
    return rows,local


def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REPOSITORY')=='zyw02/agent-architecture-evaluation','Actual cross-OS execution is hosted-only')
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['source','target'],required=True);parser.add_argument('--runtime-modules',type=Path,required=True);parser.add_argument('--node',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--source',type=Path);parser.add_argument('--calibration-only',action='store_true');args=parser.parse_args()
    require((args.phase=='source' and sys.platform.startswith('linux')) or (args.phase=='target' and sys.platform=='win32'),'An actual native Linux/Windows host is required; OS simulation is rejected')
    temporary=Path(os.environ['RUNNER_TEMP']).resolve();expected=temporary/('cross-os-source' if args.phase=='source' else 'openclaw-cross-os-result')
    require(args.output.resolve()==expected,'Cross-OS output escaped its exact disposable prefix')
    plan=load_plan();installation=verify_installation(plan['target'],args.runtime_modules,args.runtime_modules.parent/'package-lock.json')
    node_platform=json.loads(subprocess.check_output([str(args.node),'-p','JSON.stringify({platform:process.platform,node:process.versions.node,arch:process.arch})'],text=True))
    require(node_platform['platform']==('linux' if args.phase=='source' else 'win32'),'Verified Node is not executing natively on the declared host')
    args.output.mkdir();bounds=HostBounds();working=temporary/'owned-cross-os-state';working.mkdir(exist_ok=True)
    try:
        if args.phase=='source':
            for unit in range(1 if args.calibration_only else 4):
                root=working/('source-'+str(unit));data=source_unit(root,args.node,args.runtime_modules,unit,args.output);data['hardware']=bounds.summary();save(args.output/('source-'+str(unit)+'.json'),data);shutil.rmtree(root)
            save(args.output/'source-installation.json',installation);return
        require(args.source and args.source.resolve()==temporary/'cross-os-source-input','Actual Linux source artifact is required')
        require(not any(r['scenario_id'].startswith('REL-08-') and r['state'] in {'pass','fail','unsupported'} for r in records_from(DEFAULT_PLAN.parent/'results')),'Cross-OS formal results already accepted')
        provenance=args.output/'provenance';provenance.mkdir()
        for path in args.source.iterdir():
            require(path.is_file() and path.stat().st_size<=8*1024**2,'Source evidence file bound');shutil.copyfile(path,provenance/path.name)
        save(args.output/'installation.json',installation);results=[];failures=[]
        for unit in range(4):
            root=working/('target-'+str(unit));directory=provenance if unit==0 else args.output/('unit-'+str(unit));directory.mkdir(exist_ok=True)
            try:
                source=json.loads((args.source/('source-'+str(unit)+'.json')).read_text(encoding='utf8'))
                rows,local=target_unit(root,args.node,args.runtime_modules,unit,source,args.source/('source-'+str(unit)+'.tar.gz'))
                report=dict(kind='native-adapter-validation' if unit==0 else 'native-campaign-family-unit',case_id='REL-08',product='openclaw',full_campaign_coverage=unit!=0,
                    runtime_identity=installation['installed_build'],controller_sha256=hashes(),observations=rows,validation_complete=True,fixture_and_invocation_valid=True,
                    actual_source_os='Linux',actual_target_os='Windows',target_node_platform='win32',native_windows_job_object=True,
                    source_record_sha256=hashlib.sha256((args.source/('source-'+str(unit)+'.json')).read_bytes()).hexdigest(),actual_target_record=local,hardware=bounds.summary(),paid_model_calls=0)
                path=directory/('cross-os-calibration.json' if unit==0 else 'summary.json');save(path,report)
                if unit==0:
                    require_execution_ready(plan,'REL-08',[report])
                    if args.calibration_only:return
                else:results.extend(bind_unit(plan,'REL-08',unit,report,os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_SHA'],directory.name+'/summary.json',hashlib.sha256(path.read_bytes()).hexdigest()))
            except Exception as error:
                failures.append(dict(unit=unit,error=type(error).__name__+': '+str(error)[:2300]))
                save(directory/('incomplete-unit-'+str(unit)+'.json'),failures[-1])
                if unit==0:raise
            finally:
                shutil.rmtree(root,ignore_errors=True)
            save(args.output/'results.json',results);save(args.output/'execution.json',dict(case_id='REL-08',plan_sha256=plan['plan_sha256'],github_run_id=os.environ['GITHUB_RUN_ID'],controller_commit=os.environ['GITHUB_SHA'],completed_records=len(results),required_units=3,harness_failures=failures,full_campaign_coverage=True,paid_model_calls=0))
        require(not failures,'One or more actual cross-OS independent units remain incomplete')
    finally:
        shutil.rmtree(working,ignore_errors=True);bounds.close()
    require(sum(p.stat().st_size for p in args.output.rglob('*') if p.is_file())<=8*1024**2,'Cross-OS hosted evidence exceeds 8 MiB')


if __name__=='__main__':main()
