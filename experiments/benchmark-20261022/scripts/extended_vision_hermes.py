import json,os,sys,base64
from pathlib import Path
from configure_deepseek import configured_key
from hermes_deepseek_case import protect_diagnostics
ROOT=Path(__file__).resolve().parents[1];key=configured_key()
if not key:raise SystemExit('Missing credential')
protect_diagnostics(key)
profile=ROOT/'runtime/extended-vision-hermes';profile.mkdir(parents=True,exist_ok=True)
(profile/'config.yaml').write_text(json.dumps({'model':{'context_length':128000,'supports_vision':True},'agent':{'image_input_mode':'native'},'background_review':{'enabled':False}}))
os.environ['HERMES_HOME']=str(profile);os.environ['HERMES_RUNTIME_DIR']=str(profile/'runtime');sys.path.insert(0,str(ROOT/'sources/hermes'))
from run_agent import AIAgent
spec=json.loads((ROOT/'results/extended-vision-cases.json').read_text());records=[]
for case in spec['cases']:
    record={'case_id':case['case_id'],'sha256':case['sha256']};agent=None
    try:
        agent=AIAgent(api_key=key,base_url='https://api.deepseek.com',provider='custom',api_mode='chat_completions',model='deepseek-flash',enabled_toolsets=[],quiet_mode=True,skip_context_files=True,skip_memory=True,skip_background_review=True,max_iterations=2,max_tokens=256,reasoning_config={'enabled':False},request_overrides={'temperature':0,'extra_body':{'thinking':{'type':'disabled'}}})
        user=[{'type':'text','text':spec['prompt']},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(Path(case['path']).read_bytes()).decode()}}]
        result=agent.run_conversation(user);record.update({'text':result.get('final_response'),'messages':result.get('messages'),'api_calls':result.get('api_calls'),'failed':result.get('failed')})
    except Exception as error:record['error_type']=type(error).__name__
    finally:
        if agent is not None:agent.close()
    records.append(record);(ROOT/'raw/extended-models/vision-hermes.json').write_text(json.dumps({'framework':'hermes','entrypoint':'AIAgent.run_conversation(native image_url content)','records':records},indent=2,default=str).replace(key,'[REDACTED]'))
    print(json.dumps({'framework':'hermes','case_id':case['case_id'],'text':record.get('text'),'error_type':record.get('error_type')}),flush=True)
