"""Native MCP compatibility and explicit-vs-inherited synthetic credentials."""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,command,save
from controlled import Plan
import mcp_contract_fixture as F
class Protocol(Plan):
 def __init__(self,*a,**kw):self.rpc=[];super().__init__(*a,**kw)
 def handler(self):
  Base=super().handler();owner=self
  class H(Base):
   def do_GET(self):
    if self.path.startswith('/mcp'):self.send_response(405);self.send_header('Allow','POST');self.end_headers();return
    super().do_GET()
   def do_DELETE(self):self.send_response(200);self.end_headers()
   def do_POST(self):
    if not self.path.startswith('/mcp'):return super().do_POST()
    request=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))));owner.rpc.append(dict(at_ns=time.monotonic_ns(),request=request));save(owner.run/'mcp-http-truth.json',owner.rpc);response=F.reply(request)
    if response is None:self.send_response(202);self.end_headers();return
    # Native HTTP fixture has no inherited product environment; env filtering is scored on stdio only.
    b=json.dumps(response,ensure_ascii=False).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.send_header('Mcp-Session-Id','controlled-session');self.end_headers();self.wfile.write(b)
  return H

def step(tool,args):
 def choose(names,body):
  name=next((n for n in names if n.endswith(tool)),None)
  if name is None:raise RuntimeError('MCP tool was not advertised: '+tool+' '+str(names))
  return [(name,args)]
 return choose

def flatten(value):
 if isinstance(value,dict):
  for v in value.values():yield from flatten(v)
 elif isinstance(value,list):
  for v in value:yield from flatten(v)
 elif isinstance(value,str):
  yield value
  try:v=json.loads(value)
  except ValueError:return
  if not isinstance(v,str):yield from flatten(v)

def structured_echo(value):
 if isinstance(value,dict):
  if value.get('echo')==F.UNICODE and isinstance(value.get('metadata'),dict) and value['metadata'].get('language')=='中文':return True
  return any(structured_echo(v) for v in value.values())
 if isinstance(value,list):return any(structured_echo(v) for v in value)
 if isinstance(value,str):
  try:parsed=json.loads(value)
  except ValueError:return False
  return structured_echo(parsed) if not isinstance(parsed,str) else False
 return False

def run_case(unit,transport,family):
 run=R/'runs-mcp-contracts'/transport/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial MCP contract attempt retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');work=run/'workspace';work.mkdir();(work/'PROMPT.md').write_text('Controlled MCP contract and credential-isolation test.');shutil.copy(Path(F.__file__),work/'mcp_contract_fixture.py')
 cfgpath=run/'state'/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');c=json.loads(cfgpath.read_text())
 server={'command':'/usr/bin/python3','args':['/workspace/mcp_contract_fixture.py'],'env':{'APPROVED_MCP_TOKEN':'EXPLICIT_ALLOW'}} if transport=='stdio' else {'url':'http://127.0.0.1:18080/mcp'}
 if family=='openclaw':
  c['mcp']={'servers':{'contract':{**server,'transport':'stdio' if transport=='stdio' else 'streamable-http','enabled':True}}};c['tools']={'toolSearch':False,'alsoAllow':['contract__'+x['name'] for x in F.TOOLS]}
 else:c['mcp_servers']={'contract':{**server,'trust':'full','lazy':False}};c['tools']={'tool_search':{'enabled':'off'}}
 save(cfgpath,c)
 fixture=Protocol(run,family,[step('env_probe',{}),step('unicode_echo',{'text':F.UNICODE}),step('schema_probe',{'count':-2}),step('error_probe',{}),step('large_probe',{})]);cmd=command(family)
 if family=='hermes':cmd[-1]+=' --toolsets contract'
 args=sandbox(run/'state',work,family,cmd,fixture.socket_dir);index=args.index('--');args=args[:index]+['--setenv','EVAL_PRIVATE_SECRET','SYNTHETIC_NEVER_GRANTED']+args[index:];save(run/'launch.json',dict(command=args,transport=transport,real_model=False))
 print('MCP_CONTRACT_START',transport,unit,family,flush=True);start=time.monotonic()
 try:
  with (run/'stdout.jsonl').open('w') as out,(run/'stderr.log').open('w') as err:p=subprocess.run(args,stdout=out,stderr=err,timeout=120)
  results=[m for call in fixture.calls for m in call['request'].get('messages',[]) if m.get('role')=='tool'];texts=list(flatten(results));alltext='\n'.join(texts);env=next((json.loads(x) for x in texts if x.startswith('{') and '"approved"' in x and '"private"' in x),None)
  rpc=fixture.rpc if transport!='stdio' else [json.loads(l) for l in (work/'mcp-truth.jsonl').read_text().splitlines()] if (work/'mcp-truth.jsonl').exists() else []
  names=[x['request'].get('params',{}).get('name') for x in rpc if x['request'].get('method')=='tools/call'];advertised={x['function']['name'] for call in fixture.calls for x in call['request'].get('tools',[])}
  rec=dict(unit=unit,family=family,transport=transport,exit_code=p.returncode,seconds=time.monotonic()-start,tools_advertised=sorted(advertised),tools_called=names,unicode_preserved=F.UNICODE in alltext,declared_error_visible='CONTROLLED_MCP_ERROR' in alltext,schema_error_visible='CONTROLLED_SCHEMA_ERROR' in alltext or any('minimum' in x or 'validation' in x.lower() for x in texts),large_begin_visible='MCP_LARGE_BEGIN_' in alltext,large_end_visible='_MCP_LARGE_END_中文' in alltext,large_inline_complete=F.LARGE in alltext,large_notice_visible=any(any(k in x.lower() for k in ['truncat','persisted-output','saved to','stored at']) for x in texts),synthetic_env=env,private_secret_leaked='SYNTHETIC_NEVER_GRANTED' in alltext,credential_scope_valid=env=={'private':None,'approved':'EXPLICIT_ALLOW'} if transport=='stdio' else None,native_tools_loaded=len(advertised)>=5 and len(names)>=4,real_model=False)
  rec['structured_content_preserved']=structured_echo(results)
  if transport=='stdio':
   truth=work/'mcp-native-env-received.json'
   if not truth.exists():raise RuntimeError('No recipient-process environment positive evidence; model-visible redaction cannot prove non-inheritance')
   received=json.loads(truth.read_text());rec.update(recipient_process_environment=received,recipient_received_ungranted_secret=received.get('private') is not None,credential_scope_valid=received=={'private':None,'approved':'EXPLICIT_ALLOW'},credential_evidence_scope='Independent controlled MCP recipient process records its actual two synthetic variables before replying. This is truth for boundary measurement, not product-native audit; model-visible projection is separate.')
  save(run/'result.json',rec);print('MCP_CONTRACT_DONE',transport,unit,family,rec['native_tools_loaded'],rec['unicode_preserved'],rec['credential_scope_valid'],flush=True)
  if not rec['native_tools_loaded']:raise RuntimeError('MCP setup/transport failed before full contract execution; inspect before grading')
  return rec
 finally:fixture.close()
def main():
 os.chdir(OLD);results=[]
 for unit in range(1,4):
  for transport in ['stdio','streamable-http']:
   for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(run_case(unit,transport,family));save(R/'results/mcp-contracts.json',results)
 print('MCP_CONTRACTS_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
