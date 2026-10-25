"""Same-original-unit collector control, armed at first native tool approval.

Earlier startup-timed outages did not reject OC tool spans, so their accepted
coverage cannot establish retry superiority. Original evidence is untouched.
Clone native state, share immutable installed dependencies, and positively
require actual tool spans in rejected frames before comparing recovery.
"""
import json,os,shutil,stat,time
from pathlib import Path
from runtime import R,OLD,read_config,save
from controlled import shell
from gateway import Gateway
from native_approval_workflow import approved_workflow
from run_observability import Receiver
from prepare_observability import hermes_observation_mounts
from run_observation_closure import native_session,wait_run

def clone_native(source,destination):
    mounts=[]
    def ignore(directory,names):
        skipped=[]
        for name in names:
            p=Path(directory)/name
            if stat.S_ISSOCK(p.lstat().st_mode):skipped.append(name)
            elif name=='node_modules' and p.is_dir() and not p.is_symlink():
                mounts.append((p,Path('/state')/p.relative_to(source.parent)));skipped.append(name)
        return skipped
    shutil.copytree(source,destination,symlinks=True,ignore=ignore)
    return mounts

def run_case(unit,family):
    root=R/'runs-matched-collector-outage'/f'u{unit}'/family
    if(root/'result.json').exists():return json.loads((root/'result.json').read_text())
    if root.exists():raise RuntimeError('Partial matched outage retained '+str(root))
    if shutil.disk_usage(R).free<6*1024**3:raise RuntimeError('Capacity guard')
    state=root/'state';state.mkdir(parents=True);work=root/'workspace';work.mkdir()
    source=R/'runs-observability/configured'/f'u{unit}'/family/'state';vendor='openclaw' if family=='openclaw' else 'hermes'
    shared=clone_native(source/vendor,state/vendor)
    # A native state fork must carry its attested workspace as well. An empty
    # replacement correctly triggers OpenClaw's WorkspaceVanished protection.
    shutil.copytree(source.parent/'workspace',work,dirs_exist_ok=True,symlinks=True,ignore=shutil.ignore_patterns('node_modules'))
    (work/'effects.jsonl').unlink(missing_ok=True)
    config=state/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml')
    if family=='openclaw':shutil.copy2(source/'openclaw.json',config)
    cfg=read_config(config)
    if family=='hermes':
        cfg.setdefault('gateway',{}).setdefault('telemetry',{})['session_segments']={'max_turns':1,'on_compaction':False}
    save(config,cfg)
    token=f'MATCHED_COLLECTOR_U{unit}_{family}';(work/'PROMPT.md').write_text('Native same-tool-phase collector outage '+token)
    import shlex
    steps=[]
    for value in ['first','second','SHOULD_BE_DENIED']:
        code="from pathlib import Path; Path('/workspace/effects.jsonl').open('a').write("+repr(value+'\n')+"); print("+repr('NATIVE_RESULT_'+value)+")"
        steps.append(shell('python3 -c '+shlex.quote(code)))
    fixture=Receiver(root,family,steps);g=Gateway(root,family,fixture,allow_disk_warning=True)
    extra=[]
    for src,dst in shared:
        (state/dst.relative_to('/state')).mkdir(parents=True,exist_ok=True)
        extra+=['--ro-bind',str(src),str(dst)]
    if family=='hermes':
        for src,dst,ro in hermes_observation_mounts(root):extra+=['--ro-bind' if ro else '--bind',str(src),dst]
        extra+=['--setenv','HERMES_NEMO_RELAY_PLUGINS_TOML','/state/hermes/relay-plugins.toml']
    at=g.command.index('--');g.command=g.command[:at]+extra+g.command[at:]
    trigger={}
    def arm():
        trigger.update(first_native_approval_ready_monotonic=time.monotonic(),policy='Arm at the first actual native approval before resolving it; next actual trace starts five-second unavailability. Require target tool spans actually rejected before comparing recovery.')
        fixture.outage_armed=True;save(root/'matched-phase-trigger.json',trigger)
    print('MATCHED_COLLECTOR_START',unit,family,flush=True)
    try:
        g.start();response,decisions=approved_workflow(g,'Execute controlled matched-phase observation '+token,'matched-collector-'+str(unit),on_first_approval=arm)
        save(root/'native-workflow-response.json',response)
        until=time.monotonic()+15
        while fixture.first_trace_failure is None and time.monotonic()<until:time.sleep(.1)
        if fixture.first_trace_failure is None:raise RuntimeError('No actual trace rejection')
        time.sleep(max(0,fixture.down_until-time.monotonic())+20)
        if family=='hermes':
            ids=native_session(root,token)
            if len(ids)!=1:raise RuntimeError('Native session not uniquely located')
            code,_,raw=g.raw('POST','/v1/runs',{'model':'deepseek-flash','input':'Close the completed telemetry segment with a harmless same-session turn.','session_id':ids[0],'stream':False})
            start=json.loads(raw)
            if code!=202 or not start.get('run_id'):raise RuntimeError('Native segment completion admission failed')
            second=wait_run(g,start['run_id']);save(root/'native-segment-closure-response.json',second)
        time.sleep(2)
        effects=(work/'effects.jsonl').read_text().splitlines();result=dict(unit=unit,family=family,scope='Same original unit, cloned native state, new session; immutable installed dependencies shared. Supplementary matched-phase counterfactual, not new independent primary approval samples.',first_task_completed=response.get('status')==200 and effects==['first','second'],actual_trace_rejection=fixture.first_trace_failure is not None,phase_trigger=trigger,healthy_observation_seconds=20,paid_model_calls=0)
        save(root/'result.json',result);print('MATCHED_COLLECTOR_DONE',unit,family,result['first_task_completed'],flush=True);return result
    finally:g.stop();fixture.close()

def main():
    from stage_provenance import snapshot
    snapshot('matched-tool-phase-collector-outage');os.chdir(OLD)
    save(R/'evidence/matched-collector-pre-exposure.json',dict(reason='Original outage start at first trace rejected startup spans for OC but actual tool spans for H. Equal accepted coverage therefore did not establish a comparative retry difference.',planned_original_units=[1,2,3],families=['openclaw','hermes'],trigger='First actual native tool approval before decision resolution',outage_seconds=5,healthy_observation_seconds=20,validity='Must decode actually rejected target tool IDs, then compare their later accepted occurrence. A nominal outage or startup-only rejection is insufficient.',sample_scope='Same-unit controls cloned from the existing configured profiles; no multiplication of primary independent sample size.',paid_model_calls=0))
    result=[]
    for unit in range(1,4):
        for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):
            result.append(run_case(unit,family));save(R/'results/matched-collector-outage.json',result)
    print('MATCHED_COLLECTOR_COMPLETE',len(result),flush=True)

if __name__=='__main__':main()
