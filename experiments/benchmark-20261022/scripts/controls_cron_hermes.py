import json,sys,os,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
profile=R/'fixtures/extended-controls'/('hermes-cron-'+str(time.time_ns()));profile.mkdir(parents=True)
os.environ['HERMES_HOME']=str(profile)
os.environ['HERMES_RUNTIME_DIR']=str(profile/'runtime')
sys.path.insert(0,str(R/'sources/hermes'))
from cron.jobs import create_job,list_jobs,get_job,pause_job,resume_job,update_job,remove_job
cases=[]
def check(name,actual,expected):cases.append(dict(name=name,actual=actual,expected=expected,passed=actual==expected))
check('initial_empty',len(list_jobs(include_disabled=True)),0)
a=create_job('synthetic controls-a','every 1h',name='controls-a')
check('created_id',isinstance(a['id'],str) and bool(a['id']),True)
check('created_name',a['name'],'controls-a')
check('created_payload',a['prompt'],'synthetic controls-a')
b=create_job('synthetic controls-b','every 2h',name='controls-b')
check('unique_ids',a['id']!=b['id'],True)
check('list_two',len(list_jobs(include_disabled=True)),2)
pause_job(a['id'])
check('pause_persisted',get_job(a['id'])['enabled'],False)
check('paused_hidden',any(x['id']==a['id'] for x in list_jobs()),False)
resume_job(a['id'])
check('resume_visible',any(x['id']==a['id'] for x in list_jobs()),True)
update_job(a['id'],{'name':'controls-renamed'})
check('rename_persisted',get_job(a['id'])['name'],'controls-renamed')
# Store APIs reload the file on each get/list invocation; no benchmark-side cache.
check('reload_persistent_store',get_job(a['id'])['name'],'controls-renamed')
remove_job(a['id'])
check('remove_visible',any(x['id']==a['id'] for x in list_jobs(include_disabled=True)),False)
remove_job(b['id'])
check('all_removed',len(list_jobs(include_disabled=True)),0)
file=R/'raw/extended-controls/hermes.json';out=json.loads(file.read_text());out['10']=cases;file.write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(dict(passed=sum(x['passed'] for x in cases),total=len(cases),profile=str(profile))))
