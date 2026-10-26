"""Native turns for real-provider accounting; no credentials or billing oracle."""
import concurrent.futures
import hashlib
import http.client
import json
from pathlib import Path
import time

import pilot
import privacy_cases


def configure(root,scenario):
    config=pilot.configuration(root,route='mcp',tool_search=False)
    config.pop('mcp',None);config['plugins']=dict(enabled=False)
    provider=config['models']['providers'].pop('fixture');provider['baseUrl']='http://127.0.0.1:18081/v1'
    provider['apiKey']='synthetic-host-relay-placeholder';provider['models'][0].update(id='deepseek-flash',reasoning=scenario.endswith('06'),contextWindow=1000000,maxTokens=2048)
    config['models']['providers']={'deepseek':provider};config['agents']['defaults']['model']['primary']='deepseek/deepseek-flash'
    config['agents']['defaults'].update(thinkingDefault='high' if scenario.endswith('06') else 'off',timeoutSeconds=180)
    config['tools']=dict(allow=['sessions_spawn'] if scenario.endswith('04') else [],toolSearch=False)
    if scenario.endswith('04'):config['agents']['defaults']['subagents']=dict(maxConcurrent=2,maxSpawnDepth=1,runTimeoutSeconds=120)
    pilot.save(root/'config.json',config);return config


def request(prompt,key):
    begin=time.monotonic_ns();connection=http.client.HTTPConnection('127.0.0.1',18789,timeout=190)
    try:
        connection.request('POST','/v1/chat/completions',json.dumps(dict(model='openclaw',messages=[dict(role='user',content=prompt)],stream=False)),{'Content-Type':'application/json','Authorization':'Bearer '+pilot.TOKEN,'x-openclaw-session-key':key})
        response=connection.getresponse();raw=response.read(256*1024);data=json.loads(raw)
        texts=[str(c.get('message',{}).get('content','')) for c in data.get('choices',[])]
        return dict(status=response.status,content='\n'.join(texts),native_http_usage=data.get('usage'),duration_ms=(time.monotonic_ns()-begin)/1e6,response_sha256=hashlib.sha256(raw).hexdigest())
    except (OSError,ValueError,http.client.HTTPException) as error:return dict(status=None,error=type(error).__name__,duration_ms=(time.monotonic_ns()-begin)/1e6)
    finally:connection.close()


def execute(root,task,report):
    scenario=task['scenario_id'];gateway=pilot.Gateway(root,configurer=lambda root:configure(root,scenario));records=[]
    try:
        gateway.ready(timeout=90)
        for index,prompt in enumerate(task['prompts']):
            key='agent:main:accounting:'+task['task_id'].lower()+':'+str(index)
            result=request(prompt,key);history=privacy_cases.history(root,key)
            records.append(dict(session_key=key,response=result,native_history=history))
        # Child completions can return asynchronously to the retained parent.
        if scenario.endswith('04'):
            deadline=time.monotonic()+125
            while time.monotonic()<deadline:
                history=privacy_cases.history(root,records[0]['session_key']);records[0]['native_history']=history
                text=json.dumps(history)
                if 'subagent' in text and 'hasActiveSubagentRun": true' not in text and 'hasActiveRun": true' not in text:break
                time.sleep(1)
        report.update(fixture_selfcheck=dict(valid=True,task_visible_prompt_count=len(task['prompts']),credentials_in_guest=False),billing_native_turns=records,resources=gateway.sampler.summary(),native_gateway_tail=''.join(gateway.log_tail)[-3500:])
    finally:gateway.stop()
