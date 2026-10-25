"""Supplementary official Hermes session-segment closure capability guard.

Existing 36 measurements stay unchanged. A public max_turns segment setting and
an actual second turn on the same native session test whether ATIF absence was
just an open-root lifecycle observation. Fixed protocol only, no paid inference.
"""
import hashlib,json,os,sqlite3,time
from pathlib import Path
from runtime import R,OLD,configuration,read_config,save
from controlled import shell
from gateway import Gateway
from native_approval_workflow import approved_workflow
from run_observability import Receiver,TOML
from prepare_observability import hermes_observation_mounts

def native_session(run,token):
    db=run/'state/hermes/state.db';c=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
    try:return [r[0] for r in c.execute('select distinct session_id from messages where role="user" and instr(content,?)>0',(token,))]
    finally:c.close()

def wait_run(g,identity):
    until=time.monotonic()+40
    while time.monotonic()<until:
        code,_,raw=g.raw('GET','/v1/runs/'+identity,timeout=5);body=json.loads(raw)
        if body.get('status') in ['completed','failed','cancelled','interrupted']:return dict(http_status=code,body=body)
        time.sleep(.15)
    raise RuntimeError('Second native closure turn did not settle')

def run_case(unit,mode):
    run=R/'runs-observability-closure'/mode/f'u{unit}'/'hermes'
    if(run/'result.json').exists():return json.loads((run/'result.json').read_text())
    if run.exists():raise RuntimeError('Incomplete closure guard retained '+str(run))
    import shutil
    if shutil.disk_usage(R).free<6*1024**3:raise RuntimeError('Capacity guard before new closure profile')
    run.mkdir(parents=True);configuration('hermes',run/'state');work=run/'workspace';work.mkdir()
    token=f'AUDIT_CLOSURE_U{unit}_{mode}';second=f'CLOSURE_CONFIRM_U{unit}_{mode}'
    (work/'PROMPT.md').write_text('Native official closed-session observation capability guard '+token)
    cfgpath=run/'state/hermes/config.yaml';cfg=read_config(cfgpath)
    cfg['approvals']={'mode':'manual','single_query_mode':'deny','unattended_mode':'deny','timeout':90}
    cfg['monitoring']={'gateway_health_export':{'enabled':True},'export':{'otlp':{'enabled':True,'endpoint':'http://127.0.0.1:18080/otlp/v1/traces'}}}
    cfg.setdefault('telemetry',{}).setdefault('shared_metrics',{}).update(enabled=True,send=False)
    cfg.setdefault('gateway',{}).setdefault('telemetry',{})['session_segments']={'max_turns':1,'on_compaction':False}
    save(cfgpath,cfg);(run/'state/hermes/relay-plugins.toml').write_text(TOML)
    import shlex
    steps=[]
    for v in ['first','second','SHOULD_BE_DENIED']:
        payload="from pathlib import Path; Path('/workspace/effects.jsonl').open('a').write("+repr(v+'\n')+"); print("+repr('NATIVE_RESULT_'+v)+")"
        steps.append(shell('python3 -c '+shlex.quote(payload)))
    fixture=Receiver(run,'hermes',steps);g=Gateway(run,'hermes',fixture,allow_disk_warning=True)
    at=g.command.index('--');extra=[]
    for src,dst,ro in hermes_observation_mounts(run):extra+=['--ro-bind' if ro else '--bind',str(src),dst]
    extra+=['--setenv','HERMES_NEMO_RELAY_PLUGINS_TOML','/state/hermes/relay-plugins.toml']
    g.command=g.command[:at]+extra+g.command[at:]
    print('CLOSURE_GUARD_START',unit,mode,flush=True)
    try:
        g.start()
        if mode=='outage':fixture.outage_armed=True
        first,decisions=approved_workflow(g,'Execute the controlled observation workflow '+token,'closure-'+mode+'-'+str(unit));save(run/'first-turn-response.json',first)
        first_ids=native_session(run,token)
        if len(first_ids)!=1:raise RuntimeError('First native session identity is missing/ambiguous')
        before=list((run/'state/hermes/telemetry/eval-atif').glob('*.json'))
        if mode=='outage':
            until=time.monotonic()+15
            while fixture.first_trace_failure is None and time.monotonic()<until:time.sleep(.1)
            if fixture.first_trace_failure is None:raise RuntimeError('No actual failed collector trace; outage guard is invalid')
            time.sleep(max(0,fixture.down_until-time.monotonic())+6)
        # Explicit public session_id selection avoids creating another fresh
        # conversation and accidentally claiming its closure as the old one.
        code,_,raw=g.raw('POST','/v1/runs',{'model':'deepseek-flash','input':second,'session_id':first_ids[0],'stream':False},headers={'X-Hermes-Session-Key':'closure-'+mode+'-'+str(unit)})
        admission=json.loads(raw);save(run/'second-turn-admission.json',dict(status=code,body=admission))
        if code!=202 or not admission.get('run_id'):raise RuntimeError('Native second same-session admission failed')
        response=wait_run(g,admission['run_id']);save(run/'second-turn-response.json',response)
        until=time.monotonic()+8
        while not list((run/'state/hermes/telemetry/eval-atif').glob('*.json')) and time.monotonic()<until:time.sleep(.1)
        time.sleep(2)
        after_ids=native_session(run,second)
        atif=[]
        for p in sorted((run/'state/hermes/telemetry/eval-atif').glob('*.json')):
            raw=p.read_bytes();obj=json.loads(raw)
            atif.append(dict(path=str(p.relative_to(R)),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),top_level_keys=list(obj) if isinstance(obj,dict) else None))
        effects=(work/'effects.jsonl').read_text().splitlines()
        rec=dict(unit=unit,family='hermes',mode=mode,first_session_ids=first_ids,second_session_ids=after_ids,same_native_session=first_ids==after_ids,first_task_completed=first.get('status')==200 and effects==['first','second'],second_turn_completed=response['body'].get('status')=='completed',atif_files_before_second_turn=len(before),atif_files_after_second_turn=atif,actual_collector_trace_rejection=fixture.first_trace_failure is not None,receiver_attempts=len(fixture.frames),receiver_accepted=sum(x['accepted'] for x in fixture.frames),paid_model_calls=0,scope='Public official configured segment closure on an actual same-session second turn. Supplementary lifecycle guard, not new independent primary approval samples or Windows evidence. Native exported content still requires semantic inspection before claiming complete event coverage.')
        save(run/'result.json',rec);print('CLOSURE_GUARD_DONE',unit,mode,rec['same_native_session'],len(atif),flush=True)
        return rec
    finally:g.stop();fixture.close()

def main():
    from stage_provenance import snapshot
    snapshot('official-session-segment-closure-capability-guard');os.chdir(OLD)
    save(R/'evidence/session-closure-pre-exposure.json',dict(scope='Supplement tests public official segment closure, actual second turn, and local ATIF availability after collector outage; original 36 primary profiles remain unchanged.',planned_units_per_mode=3,modes=['configured','outage'],paid_model_calls=0,minimum_positive='First three native decisions yield two effects only; second completed turn must use the same native session; inspect actual ATIF tool output fields rather than searching command/request strings.',rule='Failure of harness/setup/closure assumptions is reviewed; no automatic product downgrade from absent file. No new primary weights or outcomes are inferred before native evidence.'))
    result=[]
    for unit in range(1,4):
        for mode in (['configured','outage'] if unit%2 else ['outage','configured']):
            result.append(run_case(unit,mode));save(R/'results/session-closure.json',result)
    print('SESSION_CLOSURE_GUARD_COMPLETE',len(result),flush=True)

if __name__=='__main__':main()
