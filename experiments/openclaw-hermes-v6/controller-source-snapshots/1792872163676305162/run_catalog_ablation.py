"""A03 native deferred discovery on/off with equal available MCP capability, zero paid inference."""
import json,os,subprocess,time
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,command,save
from controlled import Plan
from run_mcp_contracts import flatten
from resources import create,read,wrap
SERVER=r'''
import json,sys
n=int(sys.argv[1])
for line in sys.stdin:
 q=json.loads(line);m=q.get('method');p=q.get('params',{});result={}
 if m=='initialize':result={'protocolVersion':p.get('protocolVersion','2025-03-26'),'capabilities':{'tools':{}},'serverInfo':{'name':'catalog','version':'1'}}
 elif m=='tools/list':result={'tools':[{'name':'catalog_target_'+str(i),'description':'Read-only synthetic catalog capability '+str(i),'inputSchema':{'type':'object','properties':{}},'annotations':{'readOnlyHint':True}} for i in range(n)]}
 elif m=='tools/call':result={'content':[{'type':'text','text':'CATALOG_TARGET_OK:'+p.get('name','')}],'isError':False}
 if 'id' in q:print(json.dumps({'jsonrpc':'2.0','id':q['id'],'result':result}),flush=True)
'''
def router(target):
 def route(names,body):
  text='\n'.join(flatten([m for m in body.get('messages',[]) if m.get('role')=='tool']))
  if 'CATALOG_TARGET_OK:'+target in text:return []
  direct=next((n for n in names if n.endswith(target)),None)
  if direct:return [(direct,{})]
  if not any(m.get('role')=='tool' for m in body.get('messages',[])):
   if 'tool_search' not in names:raise RuntimeError('Target is hidden without a supported search surface')
   return [('tool_search',{'query':target})]
  # Use the name actually returned by native discovery, rather than inventing an alias.
  candidates=[]
  for text in flatten([m for m in body.get('messages',[]) if m.get('role')=='tool']):
   try:d=json.loads(text)
   except ValueError:continue
   def visit(v):
    if isinstance(v,dict):
     for k,x in v.items():
      if k in ['name','tool_name','toolName'] and isinstance(x,str) and x.endswith(target):candidates.append(x)
      else:visit(x)
    elif isinstance(v,list):
     for x in v:visit(x)
   visit(d)
  if candidates and 'tool_call' in names:
   spec=next(t['function'] for t in body['tools'] if t['function']['name']=='tool_call');props=spec.get('parameters',{}).get('properties',{});key=next((k for k in ['name','tool_name','toolName'] if k in props),'name');argkey=next((k for k in ['arguments','args','parameters'] if k in props),'arguments');return [('tool_call',{key:candidates[-1],argkey:{}})]
  raise RuntimeError('Discovery completed but target invocation contract not resolved; inspect schema/result instead of counting missing capability as savings')
 return route

def one(unit,count,enabled,family):
 label='on' if enabled else 'off';run=R/'runs-catalog-ablation'/f'n{count}-{label}'/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial catalog observation retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');work=run/'workspace';work.mkdir();(work/'PROMPT.md').write_text('Find and execute the controlled final read-only catalog capability.');(work/'catalog.py').write_text(SERVER)
 p=run/'state'/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');c=json.loads(p.read_text());server={'command':'/usr/bin/python3','args':['/workspace/catalog.py',str(count)]}
 if family=='openclaw':c['mcp']={'servers':{'evalcatalog':{**server,'transport':'stdio','enabled':True}}};c['tools']={'toolSearch':enabled,'alsoAllow':['evalcatalog__'+f'catalog_target_{i}' for i in range(count)]}
 else:c['mcp_servers']={'evalcatalog':{**server,'trust':'full','lazy':False}};c['tools']={'tool_search':{'enabled':'on' if enabled else 'off'}}
 save(p,c);fixture=Plan(run,family,router=router('catalog_target_'+str(count-1)));cmd=command(family)
 if family=='hermes':cmd[-1]+=' --toolsets evalcatalog'
 args=sandbox(run/'state',work,family,cmd,fixture.socket_dir);group=create('catalog-'+family+'-'+str(time.time_ns()));args=wrap(group,args);print('CATALOG_START',unit,count,label,family,flush=True)
 try:
  with (run/'stdout.jsonl').open('w') as out,(run/'stderr.log').open('w') as err:p=subprocess.run(args,stdout=out,stderr=err,timeout=100)
  requests=[x['request'] for x in fixture.calls if x['main']];first=requests[0] if requests else {};alltext='\n'.join(flatten([m for b in requests for m in b.get('messages',[]) if m.get('role')=='tool']));rec=dict(unit=unit,family=family,catalog_size=count,search_enabled=enabled,exit_code=p.returncode,capability_actually_invoked=('CATALOG_TARGET_OK:catalog_target_'+str(count-1)) in alltext,provider_main_requests=len(requests),initial_exposed_tool_count=len(first.get('tools',[])),initial_tool_definition_chars=len(json.dumps(first.get('tools',[]),ensure_ascii=False)),cumulative_request_chars=sum(len(json.dumps(b,ensure_ascii=False)) for b in requests),resources=read(group),real_model=False,baseline_credit=False,scope='Same native tool catalog and actual target execution. Character counts are not billed tokens; zero synthetic usage is never priced. Explains discovery tradeoffs, not main task quality.')
  save(run/'result.json',rec);print('CATALOG_DONE',unit,count,label,family,rec['capability_actually_invoked'],rec['initial_exposed_tool_count'],flush=True)
  if not rec['capability_actually_invoked']:raise RuntimeError('Capability parity failed before interpreting context reduction')
  return rec
 finally:fixture.close()
def main():
 os.chdir(OLD);results=[]
 for unit in range(1,4):
  for count in [10,100,500]:
   for enabled in [False,True]:
    for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(one(unit,count,enabled,family));save(R/'results/catalog-ablation.json',results)
 print('CATALOG_ABLATION_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
