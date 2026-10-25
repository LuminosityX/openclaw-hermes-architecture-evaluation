import json,os,pathlib,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'sources/hermes'));profile=ROOT/'runtime/extended-integration/hermes-browser';profile.mkdir(parents=True,exist_ok=True);os.environ['HERMES_HOME']=str(profile);(profile/'config.yaml').write_text(json.dumps({'security':{'allow_private_urls':True},'browser':{'cdp_url':'http://127.0.0.1:40311'},'terminal':{'backend':'local'}}))
from tools.browser_cdp_tool import browser_cdp
records=[];run_tag=time.time_ns()
def call(method,params=None,target=None):
 r=json.loads(browser_cdp(method,params,target_id=target,timeout=10,task_id='integration-bench'))
 if not r.get('success'):raise RuntimeError(str(r))
 return r['result']
target=call('Target.createTarget',{'url':'about:blank'})['targetId']
for i in range(10):
 caseid=f'hermes-{run_tag}-{i}';ref=f'订单-{i}-😀';qty=i+1
 try:
  call('Page.navigate',{'url':f'http://127.0.0.1:40310/?case={caseid}'},target)
  for _ in range(50):
   r=call('Runtime.evaluate',{'expression':"Boolean(document.querySelector('#submit'))",'returnByValue':True},target)
   if r['result'].get('value'):break
   time.sleep(.02)
  expression=f"document.querySelector('#reference').value={json.dumps(ref)};document.querySelector('#quantity').value='{qty}';document.querySelector('#submit').click();"
  call('Runtime.evaluate',{'expression':expression,'returnByValue':True},target)
  state=''
  for _ in range(50):
   state=call('Runtime.evaluate',{'expression':"document.querySelector('#status').textContent",'returnByValue':True},target)['result'].get('value')
   if state=='Saved':break
   time.sleep(.02)
  events=[json.loads(x) for x in (ROOT/'raw/extended-integration/browser-events.jsonl').read_text().splitlines()];records.append({'case':i,'caseid':caseid,'ref':ref,'qty':qty,'state':state,'passed':state=='Saved' and any(e['case'][0]==caseid and e['reference'][0]==ref and e['quantity'][0]==str(qty) for e in events)})
 except Exception as e:records.append({'case':i,'passed':False,'error':str(e)})
(ROOT/'raw/extended-integration/hermes-browser.json').write_text(json.dumps({'framework':'hermes','records':records,'entrypoints':['tools/browser_cdp_tool.py:browser_cdp']},indent=2));print(json.dumps({'passed':sum(x['passed'] for x in records),'total':len(records)}))
