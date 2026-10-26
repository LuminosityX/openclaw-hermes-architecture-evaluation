"""Actual state/workspace relocation and native process UID migration, all owned."""
import hashlib
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess

import mechanism_cases as mechanism
from operation_fixture import OperationFixture
import pilot
import service_path_cases as service

SCENARIOS={f'REL-06-S{i:02}':name for i,name in enumerate(['state-only','workspace-only','uid-only','combined'],1)}


def owned_chown(path,uid):
    """Never follow links or leave the explicitly owned /scratch subtree."""
    if path==pilot.BASE or pilot.BASE not in path.parents:raise RuntimeError('Ownership mutation is outside the owned fixture paths')
    if not path.exists() and not path.is_symlink():return
    # Without DAC override, changing a 0700 parent to another UID before walking
    # it revokes our own traversal access. Transfer children first; restoring
    # ownership to the controller uses the opposite order to regain access.
    restoring=uid==os.geteuid()
    if restoring:os.chown(path,uid,uid,follow_symlinks=False)
    if path.is_dir() and not path.is_symlink():
        for child in path.iterdir():owned_chown(child,uid)
    if not restoring:os.chown(path,uid,uid,follow_symlinks=False)


def query(operations):
    path=pilot.BASE/'run/relocation-wire.json'
    pilot.save(path,dict(shared_token=pilot.TOKEN,operations=operations))
    result=subprocess.run([pilot.NODE,'/driver/trace_access_probe.mjs',str(path)],capture_output=True,text=True,timeout=80)
    if not result.stdout.strip():raise RuntimeError('Public relocation probe emitted no result: '+result.stderr[-800:])
    data=json.loads(result.stdout)
    if result.returncode or data.get('harness_error'):raise RuntimeError('Public relocation probe failed: '+json.dumps(data)[:1500])
    return data


def configure(root):
    config=service.configure(root)
    config['tools']['allow'].extend(['read','exec'])
    config['tools']['exec']=dict(host='gateway',security='full',ask='off')
    config['tools']['fs']=dict(workspaceOnly=False)
    plugin=root/'composition-a/index.js';source=plugin.read_text()
    source=source.replace('  const announce=async(path,extra={})=>{',
        '''  const storage=process.env.OPENCLAW_STATE_DIR+'/owned-extension-counter.json';
  const previous=fs.existsSync(storage)?JSON.parse(fs.readFileSync(storage,'utf8')).counter:0;
  const persistedCounter=previous+1;fs.writeFileSync(storage,JSON.stringify({counter:persistedCounter}));
  const announce=async(path,extra={})=>{''')
    source=source.replace('token:args.token,owner,pid:process.pid,','token:args.token,owner,pid:process.pid,uid:process.getuid?.(),persisted_counter:persistedCounter,')
    plugin.write_text(source)
    (root/'workspace/owned-workspace-canary.txt').write_text('WORKSPACE_RELOCATION_CANARY_a8412')
    pilot.save(root/'config.json',config)
    return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];fixture=OperationFixture();gateway=None;assertions=[];metadata={};target=None
    token='PILOT_RELOCATION_'+scenario.replace('-','_')+'_U'+str(unit);session=token.lower()+'_persistent'
    uid_change=mode in {'uid-only','combined'};state_move=mode in {'state-only','combined'};workspace_move=mode in {'workspace-only','combined'}
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-public-records','independent-plugin-receipts','ownership-and-path-manifest']))
    try:
        original=root/'original';gateway=pilot.Gateway(original,configurer=configure);gateway.ready()
        before=token+'_BEFORE';fixture.register(before);positive=gateway.request(before,session_key=session)
        if not positive['accepted'] or fixture.receipts.get(before)!=1:raise RuntimeError('Native pre-relocation task control failed')
        before_events=[e for e in fixture.events if e['kind']=='effect-commit' and e.get('token')==before]
        if len(before_events)!=1 or before_events[0].get('persisted_counter')!=1:raise RuntimeError('Owned persistent-extension fixture did not initialize')
        scheduled_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(timespec='milliseconds').replace('+00:00','Z')
        cron=query([dict(method='cron.add',params=dict(name='Owned migration schedule '+token,enabled=False,
            schedule=dict(kind='at',at=scheduled_at),sessionTarget='main',wakeMode='next-heartbeat',
            payload=dict(kind='systemEvent',text='SCHEDULED_RELOCATION_CANARY_'+token)))])
        created=cron['responses'][0]['result']
        if not created.get('ok'):raise RuntimeError('Native scheduled-state control failed: '+json.dumps(created)[:1500])
        cron_id=created['payload'].get('id') or created['payload'].get('job',{}).get('id')
        if not cron_id:raise RuntimeError('Native cron control did not return a stable job ID')
        previous=query([dict(method='chat.history',params=dict(sessionKey='agent:main:pilot:'+session,limit=100))])
        prior=previous['responses'][0]['result']['payload'];session_id=prior.get('sessionId')
        if not session_id:raise RuntimeError('Native prior session identity missing')
        row.update(fixture_validated=True,native_invoked=True)
        gateway.stop();config=json.loads((original/'config.json').read_text());target=original
        if state_move:
            target=root/'new-deployment';target.mkdir();shutil.move(str(original/'state'),str(target/'state'))
        workspace=original/'workspace'
        if workspace_move:
            moved=root/'moved-workspace';shutil.move(str(workspace),str(moved));workspace=moved
            config['agents']['defaults']['workspace']=str(workspace)
        config['logging']['file']=str(target/'gateway-native.log');pilot.save(target/'config.json',config)
        native_uid=1001 if uid_change else 0
        if uid_change:
            for path in [root,pilot.BASE/'home',pilot.BASE/'cache',pilot.BASE/'tmp']:owned_chown(path,native_uid)
        def drop_identity():
            os.setgroups([]);os.setgid(native_uid);os.setuid(native_uid)
        env=dict(os.environ,OPENCLAW_STATE_DIR=str(target/'state'),OPENCLAW_CONFIG_PATH=str(target/'config.json'),
            OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_DISABLE_BUNDLED_PLUGINS='1')
        doctor=subprocess.run([pilot.NODE,pilot.CLI,'doctor','--fix','--non-interactive'],env=env,
            capture_output=True,text=True,timeout=90,preexec_fn=drop_identity if uid_change else None)
        metadata['native_doctor']=dict(returncode=doctor.returncode,stdout=doctor.stdout[-8000:],stderr=doctor.stderr[-2000:])
        metadata.update(source_state=str(original/'state'),target_state=str(target/'state'),workspace_path=str(workspace),
            source_uid=0,target_uid=native_uid,core_files_modified=0,shared_runtime_copied=False,
            ownership_policy='Only owned fixture roots and scratch home/cache/tmp are recursively re-owned without following links. The immutable runtime is never chowned or copied.')
        # The root controller deliberately lacks DAC override and must not read
        # the new owner's private config after Doctor changes its permissions.
        # The actual native child reads the effective on-disk config as its UID.
        gateway=pilot.Gateway(target,configurer=lambda _:config,process_uid=native_uid if uid_change else None);gateway.ready()
        after=token+'_AFTER';fixture.register(after);continued=gateway.request(after,session_key=session)
        effect=[e for e in fixture.events if e['kind']=='effect-commit' and e.get('token')==after]
        check('native-session-task-continues-after-relocation',continued['accepted'] and fixture.receipts.get(after)==1)
        check('actual-native-process-uid-matches-new-owner',len(effect)==1 and effect[0].get('uid')==native_uid)
        check('owned-extension-persistence-continues',len(effect)==1 and effect[0].get('persisted_counter')==2)
        transcript=query([dict(method='chat.history',params=dict(sessionKey='agent:main:pilot:'+session,limit=100))])
        history=transcript['responses'][0]['result'];payload=history.get('payload',{})
        check('same-native-session-identity-preserved',history.get('ok') and payload.get('sessionId')==session_id)
        check('pre-and-post-relocation-history-visible',all(marker in json.dumps(payload) for marker in [before,after]))
        schedules=query([dict(method='cron.list',params=dict(includeDisabled=True))])
        listing=schedules['responses'][0]['result']
        check('disabled-scheduled-state-identity-preserved',listing.get('ok') and cron_id in json.dumps(listing) and 'SCHEDULED_RELOCATION_CANARY_'+token in json.dumps(listing))
        read=token+'_WORKSPACE';fixture.plan(read,'read',dict(path=str(workspace/'owned-workspace-canary.txt')),'WORKSPACE_RELOCATION_CANARY_a8412')
        readable=gateway.request(read,session_key=session)
        check('migrated-workspace-content-readable',readable['accepted'])
        cwd=token+'_CWD';fixture.plan(cwd,'exec',dict(command='pwd',yieldMs=10000),str(workspace))
        located=gateway.request(cwd,session_key=session)
        check('native-execution-uses-declared-new-workspace',located['accepted'])
        metadata.update(prior_session_id=session_id,post_session_id=payload.get('sessionId'),native_schedule_id=cron_id,
            native_history=transcript,native_schedules=schedules,
            workspace_read_returns=fixture.tool_returns.get(read),cwd_returns=fixture.tool_returns.get(cwd),
            relocation_scope='Same actual hosted machine, explicit native process UID change where selected. No cross-OS or independent-host migration is inferred.')
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            metadata=metadata,independent_events=fixture.events,independent_receipts=fixture.receipts,
            resources=None if uid_change else gateway.sampler.summary(),
            resource_unavailable_reason='After UID drop, controller lacks CAP_SYS_PTRACE for target smaps. Do not interpret inaccessible PSS as zero.' if uid_change else None,
            paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:3000],metadata=metadata)
    finally:
        if gateway:gateway.stop()
        fixture.close()
        if uid_change:
            for path in [root,pilot.BASE/'home',pilot.BASE/'cache',pilot.BASE/'tmp']:owned_chown(path,0)
        shutil.rmtree(root,ignore_errors=True)
        row['owned_state_retained']=root.exists()
    return row
