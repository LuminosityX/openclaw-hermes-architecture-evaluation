import json,os,sys,time,signal
from pathlib import Path
R=Path(__file__).resolve().parents[1];profile=R/'runtime/control-hermes';profile.mkdir(parents=True,exist_ok=True);os.environ['HERMES_HOME']=str(profile);os.environ['HERMES_RUNTIME_DIR']=str(profile/'runtime');os.environ['TERMINAL_ENV']='local';os.environ['TERMINAL_CWD']=str(R)
(profile/'config.yaml').write_text(json.dumps({'terminal':{'backend':'local','cwd':str(R)},'background_review':{'enabled':False}}));sys.path.insert(0,'/root/output/openclaw-hermes-benchmark-20261022/sources/hermes')
from tools.terminal_tool import terminal_tool,cleanup_all_environments
terminal_tool('printf READY',timeout=5,task_id='nf-warmup',workdir=str(R));records=[]
def alive(pid):
    try:return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[0]!='Z'
    except OSError:return False
for i in range(5):
    prefix=profile/f'beat-{i}';start=time.monotonic();result=terminal_tool(f'/usr/bin/python3 {R}/scripts/heartbeat.py {prefix}',timeout=1,task_id=f'nf-timeout-{i}',workdir=str(R));end=time.monotonic();time.sleep(.3)
    pids=json.loads(Path(str(prefix)+'.pids').read_text()) if Path(str(prefix)+'.pids').exists()else [];survivors=[p for p in pids if alive(p)];beat=Path(str(prefix)+'.beat');before=beat.read_text()if beat.exists()else None;time.sleep(.25);after=beat.read_text()if beat.exists()else None
    for pid in survivors:
        try:os.kill(pid,signal.SIGKILL)
        except OSError:pass
    rec={'framework':'hermes','sample':i,'wall_ms':(end-start)*1000,'configured_timeout_ms':1000,'started':len(pids)==2,'pids':pids,'surviving_processes':len(survivors),'heartbeat_continued':before!=after,'result':json.loads(result)};records.append(rec);(R/'raw/timeout-hermes.json').write_text(json.dumps(records,indent=2));print(json.dumps({'sample':i,'wall_ms':rec['wall_ms'],'started':rec['started'],'survivors':len(survivors)}),flush=True)
cleanup_all_environments()
