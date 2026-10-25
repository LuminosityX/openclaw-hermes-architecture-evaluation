"""Run paired real-model cases through native Hermes in one source process."""
import json,os,sys,time,subprocess
from pathlib import Path
from configure_deepseek import configured_key
from hermes_deepseek_case import protect_diagnostics
ROOT=Path(__file__).resolve().parents[1]
key=configured_key()
if not key:raise SystemExit('DeepSeek credential not configured')
protect_diagnostics(key)
profile=ROOT/'runtime/extended-model-hermes';profile.mkdir(parents=True,exist_ok=True)
(profile/'config.yaml').write_text(json.dumps({'model':{'context_length':128000},'terminal':{'backend':'local'},'tools':{'tool_search':{'enabled':'off'}},'background_review':{'enabled':False}}))
os.environ['HERMES_HOME']=str(profile);os.environ['HERMES_RUNTIME_DIR']=str(profile/'runtime')
sys.path.insert(0,str(ROOT/'sources/hermes'))
from run_agent import AIAgent
from tools import skills_tool
cases=json.loads((ROOT/'results/extended-model-cases.json').read_text())['cases']
output_dir=ROOT/'raw/extended-models';output_dir.mkdir(parents=True,exist_ok=True)
for case in cases:
    target=output_dir/f'hermes-{case["case_id"]}.json'
    if target.exists():continue
    workspace=Path(case['workspaces']['hermes']);os.chdir(workspace)
    skills_tool.SKILLS_DIR=workspace/'skills';skills_tool.clear_skills_cache()
    agent=None;start=time.monotonic();record={'framework':'hermes','case_id':case['case_id'],'row':case['row'],'model':'deepseek-flash'}
    try:
        agent=AIAgent(api_key=key,base_url='https://api.deepseek.com',provider='custom',api_mode='chat_completions',model='deepseek-flash',enabled_toolsets=['terminal','file','skills'],quiet_mode=True,skip_context_files=True,skip_memory=True,skip_background_review=True,max_iterations=10,max_tokens=1536,cwd=str(workspace),reasoning_config={'enabled':False},request_overrides={'temperature':0,'extra_body':{'thinking':{'type':'disabled'}}})
        result=agent.run_conversation(case['prompt']);record.update({'completed':result.get('completed'),'failed':result.get('failed'),'final_response':result.get('final_response'),'messages':result.get('messages'),'usage':{k:result.get(k) for k in ['api_calls','prompt_tokens','completion_tokens','cache_read_tokens','reasoning_tokens']}})
    except Exception as exc:record.update({'error_type':type(exc).__name__})
    finally:
        if agent is not None:
            try:agent.close()
            except Exception as exc:record['cleanup_error']=type(exc).__name__
    actual=None
    try:actual=json.loads((workspace/case['output_file']).read_text())
    except (ValueError,OSError):pass
    record.update({'actual':actual,'correct':actual==case['expected'],'wall_seconds':time.monotonic()-start})
    target.write_text(json.dumps(record,ensure_ascii=False,indent=2,default=str).replace(key,'[REDACTED]'))
    print(json.dumps({k:record[k] for k in ['framework','case_id','correct','wall_seconds']}),flush=True)
