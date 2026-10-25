import concurrent.futures,json,time,uuid,sys
from pathlib import Path
import requests
R=Path(__file__).resolve().parents[1];BASE={'openclaw':'http://127.0.0.1:40491','hermes':'http://127.0.0.1:40492'};AUTH={'Authorization':'Bearer local-nonfunctional-benchmark'}
def control(framework,run_id,fault=0):requests.post('http://127.0.0.1:40490/control',json={'framework':framework,'run_id':run_id,'fault':fault},timeout=5).raise_for_status()
def request(framework,run_id,kind='text',stream=True):
    token='NF_'+uuid.uuid4().hex[:10];model='openclaw'if framework=='openclaw'else'deepseek-flash'
    if kind=='tool':
        workspace=R/'workspaces'/framework;input_path=workspace/(token+'.input.json');output_path=workspace/(token+'.output.json');input_path.write_text(json.dumps({'values':[13,27,9,41,6]}));prompt=f'请使用终端工具读取文件{input_path}，计算values的总和，把结果写为JSON文件{output_path}，格式为{{"sum":96}}。最后只回复 {token}。必须真实读写文件，不要只口头回答。'
    else:prompt=f'这是短文本响应测试。请只回复下面的标记，不要解释，不要调用工具：{token}'
    payload={'model':model,'messages':[{'role':'user','content':prompt}],'stream':stream,'max_tokens':512,'temperature':0,'user':run_id+'-'+token};start=time.monotonic();first=None;answer='';events=[];status=None;error=None
    try:
        with requests.post(BASE[framework]+'/v1/chat/completions',headers=AUTH,json=payload,stream=stream,timeout=(10,150)) as response:
            status=response.status_code
            if stream:
                for raw in response.iter_lines(chunk_size=1):
                    if not raw:continue
                    line=raw.decode('utf-8','replace');events.append(line)
                    if line.startswith('data: ')and line[6:]!='[DONE]':
                        try:
                            part=json.loads(line[6:])
                            for choice in part.get('choices',[]):
                                text=(choice.get('delta')or{}).get('content')or''
                                if text and first is None:first=time.monotonic()
                                answer+=text
                        except (ValueError,TypeError):pass
            else:
                body=response.json();events.append(body)
                for choice in body.get('choices',[]):answer+=(choice.get('message')or{}).get('content')or''
    except Exception as exc:error=type(exc).__name__
    end=time.monotonic();artifact_correct=None
    if kind=='tool':
        try:artifact_correct=json.loads(output_path.read_text())=={'sum':96}
        except (ValueError,OSError):artifact_correct=False
    rec={'framework':framework,'run_id':run_id,'kind':kind,'token':token,'status':status,'start':start,'end':end,'first_text_ms':(first-start)*1000 if first else None,'total_ms':(end-start)*1000,'answer':answer,'correct':status==200 and token in answer and (artifact_correct is not False),'artifact_correct':artifact_correct,'error':error,'events':events}
    target=R/'raw'/f'http-{run_id}-{token}.json';target.write_text(json.dumps(rec,ensure_ascii=False,indent=2));print(json.dumps({k:rec[k]for k in['framework','run_id','first_text_ms','total_ms','correct','status','error']}),flush=True);return rec
def run():
    records=[]
    for framework in ['hermes','openclaw']:
        run_id=framework+'-warmup';control(framework,run_id);records.append(request(framework,run_id))
    for i in range(3):
        for framework in (['openclaw','hermes']if i%2==0 else['hermes','openclaw']):
            run_id=f'{framework}-text-{i}';control(framework,run_id);records.append(request(framework,run_id))
    for i in range(2):
        for framework in ['hermes','openclaw']:
            run_id=f'{framework}-tool-{i}';control(framework,run_id);records.append(request(framework,run_id,'tool'))
    for fault in [429,503]:
        for framework in ['openclaw','hermes']:
            run_id=f'{framework}-fault-{fault}';control(framework,run_id,fault);records.append(request(framework,run_id))
    for batch in range(2):
        for framework in (['openclaw','hermes']if batch==0 else['hermes','openclaw']):
            run_id=f'{framework}-concurrency4-{batch}';control(framework,run_id);start=time.monotonic()
            with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:group=list(pool.map(lambda _:request(framework,run_id),range(4)))
            end=time.monotonic();records.extend(group);(R/'raw'/f'batch-{run_id}.json').write_text(json.dumps({'framework':framework,'run_id':run_id,'start':start,'end':end,'makespan_ms':(end-start)*1000,'completed':sum(r['correct']for r in group),'requests':len(group),'throughput_per_second':sum(r['correct']for r in group)/(end-start)},indent=2))
    (R/'results/http-runs.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
if __name__=='__main__':run()
