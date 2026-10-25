import json,sys,os
from pathlib import Path
R=Path(__file__).resolve().parents[1];os.environ['HERMES_HOME']=str(R/'runtime/extended-resources/hermes/home');sys.path.insert(0,str(R/'sources/hermes'))
from agent.auxiliary_client import resolve_provider_client
c,model=resolve_provider_client('custom',model='local-fixture',explicit_base_url='http://127.0.0.1:38773/v1',explicit_api_key='synthetic-local-fixture-key',api_mode='chat_completions')
cases=['plain','unicode','multiline','system','multiturn','stream','tool','json','max_tokens','temperature'];out=[]
for case in cases:
 msgs=[{'role':'user','content':'CASE:'+case}];extra={}
 if case=='unicode':msgs[0]['content']+=' 中文测试🐱'
 if case=='multiline':msgs[0]['content']+=' line one\nline two'
 if case=='system':msgs.insert(0,{'role':'system','content':'Synthetic instruction.'})
 if case=='multiturn':msgs=[{'role':'user','content':'first'},{'role':'assistant','content':'ack'}]+msgs
 if case=='tool':extra['tools']=[{'type':'function','function':{'name':'lookup','description':'synthetic','parameters':{'type':'object','properties':{'key':{'type':'string'}},'required':['key']}}}]
 if case=='json':extra['response_format']={'type':'json_object'}
 if case=='max_tokens':extra['max_tokens']=8
 if case=='temperature':extra['temperature']=0
 try:
  r=c.chat.completions.create(model=model,messages=msgs,extra_headers={'X-Benchmark-Framework':'hermes'},**extra,**({'stream':True}if case=='stream'else{}))
  if case=='stream':
   text=''.join(ch.choices[0].delta.content or''for ch in r if ch.choices);detail=json.loads(text);ok=detail['valid']and detail['case']==case
  elif case=='tool':
   msg=r.choices[0].message;detail=msg.model_dump();ok=msg.tool_calls[0].function.name=='lookup'and json.loads(msg.tool_calls[0].function.arguments)['key']=='synthetic'
  else:detail=json.loads(r.choices[0].message.content);ok=detail['valid']and detail['case']==case
  out.append({'name':case,'passed':bool(ok),'details':detail})
 except Exception as e:out.append({'name':case,'passed':False,'error':repr(e)})
(R/'raw/extended-resources/provider-hermes.json').write_text(json.dumps(out,indent=2));print(json.dumps({'passed':sum(x['passed']for x in out),'total':len(out)}));c.close()
