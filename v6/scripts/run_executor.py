"""X04: finite-state executor through each public integration: native harness versus ProviderProfile/ACP.
The initial core-fork draft was not executed and is retained only as design history; it is not the Hermes baseline.
"""
import ast,hashlib,json,os,shutil,subprocess,time,copy
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,command,save
from controlled import Plan
from run_state_ops import cli,db_inventory
OC=r'''
import fs from 'node:fs';
export default {id:'evalfsa',name:'Finite state executor',register(api){api.registerAgentHarness({id:'eval-fsa',label:'Finite state executor',autoSelection:{providerIds:['fixed-fsa']},executionEnvironment:'host-only',supports(ctx){return ctx.provider==='fixed-fsa'?{supported:true,priority:100000}:{supported:false,reason:'different provider'};},async runAttempt(p){
 const match=p.prompt.match(/EVAL_FSA:(\{[^\n]+\})/);if(!match)throw new Error('Only controlled FSA inputs supported');const input=JSON.parse(match[1]);
 if(!/^[A-Za-z0-9_-]+$/.test(input.id))throw new Error('Invalid controlled artifact id');let states=['received','validated'];const valid=Number.isInteger(input.value)&&input.value>=0;let out={id:input.id,status:valid?'completed':'rejected',value:valid?input.value*2:null};states.push(valid?'executed':'rejected');if(p.abortSignal?.aborted)throw new Error('FSA aborted');fs.writeFileSync('/workspace/fsa-'+input.id+'.json',JSON.stringify({...out,states}));if(p.abortSignal?.aborted)throw new Error('FSA aborted');
 const text='FSA_RESULT:'+JSON.stringify(out);const a={role:'assistant',content:[{type:'text',text}],api:'openai-completions',provider:'fixed-fsa',model:'deepseek-flash',usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:'stop',timestamp:Date.now()};
 return {terminal:{kind:'ok'},sessionIdUsed:p.sessionId,sessionFileUsed:p.sessionFile,agentHarnessId:'eval-fsa',messagesSnapshot:[a],assistantTexts:[text],lastAssistant:a,toolMetas:[],didSendViaMessagingTool:false,messagingToolSentTexts:[],messagingToolSentMediaUrls:[],messagingToolSentTargets:[],cloudCodeAssistFormatError:false,replayMetadata:{hadPotentialSideEffects:true,replaySafe:false},itemLifecycle:{startedCount:0,completedCount:0,activeCount:0}};
}});}};
'''
HPLUGIN=r'''
from providers import register_provider
from providers.base import ProviderProfile
class FSAProfile(ProviderProfile):
 def create_client(self,**kwargs):
  from agent.copilot_acp_client import CopilotACPClient
  return CopilotACPClient(**kwargs)
register_provider(FSAProfile(name='fixed-fsa',display_name='Controlled finite-state executor',api_mode='chat_completions',auth_type='external_process',base_url='acp://fixed-fsa',process_command='/usr/bin/python3',process_args=('/workspace/fsa_acp.py',),fallback_models=('deepseek-flash',),supports_model_listing=False,supports_health_check=False,supports_streaming=False))
'''
HACP=r'''
import json,re,sys
sid='controlled-fsa-session'
def send(d):print(json.dumps(d,ensure_ascii=False),flush=True)
def response(r,value):send({'jsonrpc':'2.0','id':r['id'],'result':value})
for line in sys.stdin:
 r=json.loads(line);method=r.get('method');p=r.get('params',{})
 if method=='initialize':response(r,{'protocolVersion':p.get('protocolVersion',1),'agentCapabilities':{'loadSession':False,'promptCapabilities':{'image':False,'audio':False,'embeddedContext':False}},'agentInfo':{'name':'controlled-fsa','version':'1.0'}})
 elif method=='session/new':response(r,{'sessionId':sid,'models':{'currentModelId':'deepseek-flash','availableModels':[{'modelId':'deepseek-flash','name':'Controlled finite-state route'}]}})
 elif method=='session/set_model':response(r,{})
 elif method=='session/prompt':
  text='\n'.join(x.get('text','') for x in p.get('prompt',[]) if isinstance(x,dict));match=re.search(r'EVAL_FSA:(\{[^\n]+\})',text)
  if not match:raise RuntimeError('Not a controlled FSA input')
  data=json.loads(match.group(1));valid=type(data.get('value')) is int and data['value']>=0;out=dict(id=data['id'],status='completed' if valid else 'rejected',value=data['value']*2 if valid else None);artifact=dict(out,states=['received','validated','executed' if valid else 'rejected'])
  send({'jsonrpc':'2.0','id':'fsa-file-write','method':'fs/write_text_file','params':{'sessionId':sid,'path':'/workspace/fsa-'+data['id']+'.json','content':json.dumps(artifact)}})
  while True:
   ack=json.loads(sys.stdin.readline())
   if ack.get('id')=='fsa-file-write':
    if 'error' in ack:raise RuntimeError('Native ACP file bridge rejected write: '+str(ack['error']))
    break
  send({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':sid,'update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'FSA_RESULT:'+json.dumps(out)}}}});response(r,{'stopReason':'end_turn'})
 elif method=='session/cancel':pass
 elif 'id' in r:response(r,{})
'''

def run_case(unit,family):
 run=R/'runs-executor'/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial executor route attempt retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');work=run/'workspace';work.mkdir();input=dict(id='case'+str(unit),value=[17,83,-1][unit-1]);(work/'PROMPT.md').write_text('EVAL_FSA:'+json.dumps(input));p=run/'state'/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');c=json.loads(p.read_text());baseline_config=copy.deepcopy(c);extra=[]
 if family=='openclaw':
  c['models']['providers']['fixed-fsa']=json.loads(json.dumps(c['models']['providers']['deepseek']));
  c['agents']['defaults'].setdefault('models',{})['fixed-fsa/deepseek-flash']=json.loads(json.dumps(c['agents']['defaults']['models']['deepseek/deepseek-flash']));c['agents']['defaults'].setdefault('modelPolicy',{})['allow']=['deepseek/deepseek-flash','fixed-fsa/deepseek-flash']
  c['agents']['defaults']['model']['primary']='fixed-fsa/deepseek-flash';c.setdefault('tools',{}).setdefault('fs',{})['workspaceOnly']=False
  plugin=run/'state/plugins/evalfsa';plugin.mkdir(parents=True);save(plugin/'package.json',{'name':'finite-state-executor','version':'1.0.0','type':'module','openclaw':{'extensions':['./index.js']}});save(plugin/'openclaw.plugin.json',{'id':'evalfsa','name':'Finite state executor','activation':{'onStartup':True,'onAgentHarnesses':['eval-fsa']},'configSchema':{'type':'object','properties':{},'additionalProperties':False}});(plugin/'index.js').write_text(OC);c['plugins']={'allow':['evalfsa'],'load':{'paths':['/state/plugins/evalfsa']},'entries':{'evalfsa':{'enabled':True}}};save(p,c)
  command_install=sandbox(run/'state',work,family,cli(family,['plugins','install','--force','--accept-capabilities','--link','/state/plugins/evalfsa']));result=subprocess.run(command_install,capture_output=True,text=True,timeout=90);save(run/'native-install.json',dict(exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr))
  if result.returncode:raise RuntimeError('Harness plugin not installed')
 else:
  plugin=run/'state/hermes/plugins/model-providers/eval-fsa';plugin.mkdir(parents=True);(plugin/'__init__.py').write_text(HPLUGIN);save(plugin/'plugin.yaml',dict(name='eval-fsa',version='1.0.0',description='Public external-process provider for the controlled finite-state executor'));(work/'fsa_acp.py').write_text(HACP);c['model'].update(provider='fixed-fsa',base_url='acp://fixed-fsa',api_mode='chat_completions');save(p,c)
 fixture=Plan(run,family,[]);native=command(family)
 if family=='openclaw':native=cli(family,['agent','--local','--agent','main','--session-id','fsa-'+str(unit),'--message',(work/'PROMPT.md').read_text(),'--json','--timeout','60'])
 else:native[-1]=native[-1].replace('--provider deepseek','--provider fixed-fsa')
 cmd=sandbox(run/'state',work,family,native,fixture.socket_dir,extra);print('EXECUTOR_START',unit,family,flush=True)
 try:
  with (run/'stdout.jsonl').open('w') as out,(run/'stderr.log').open('w') as err:result=subprocess.run(cmd,stdout=out,stderr=err,timeout=100)
  f=work/('fsa-'+input['id']+'.json');got=json.loads(f.read_text()) if f.exists() else {};expected=dict(id=input['id'],status='completed' if input['value']>=0 else 'rejected',value=input['value']*2 if input['value']>=0 else None,states=['received','validated','executed' if input['value']>=0 else 'rejected']);inventory=db_inventory(run/'state','EVAL_FSA:');save(run/'native-state-inventory.json',inventory)
  rec=dict(unit=unit,family=family,exit_code=result.returncode,expected=expected,actual=got,passed=result.returncode==0 and got==expected,persisted_user_history=any(x.get('token_hits') for x in inventory),provider_requests=sum(x['main'] for x in fixture.calls),implementation_route='public native host-only agent harness plugin' if family=='openclaw' else 'public external-process ProviderProfile plus native ACP client and fs bridge',route_class=0,unmodified_product_credit=True,real_model=False,scope='Authorized local finite-executor integration; not a sandbox-equivalence test. OpenClaw host-only harness runs through full embedded CLI with explicit local full filesystem policy; its rejection under workspace-only headless policy is retained as a separate native guard positive. Ordinary model route is verified independently.')
  if family=='hermes':save(p,baseline_config)
  (work/'NORMAL.md').write_text('Return exactly CONTROLLED_COMPLETE through the ordinary unmodified native execution route.');normal=sandbox(run/'state',work,family,command(family,prompt='/workspace/NORMAL.md'),fixture.socket_dir,extra);control=subprocess.run(normal,capture_output=True,text=True,timeout=100);save(run/'ordinary-route-control.json',dict(exit_code=control.returncode,stdout=control.stdout,stderr=control.stderr));rec['ordinary_route_preserved']=control.returncode==0 and 'CONTROLLED_COMPLETE' in control.stdout;rec['passed']=rec['passed'] and rec['ordinary_route_preserved'];rec['fsa_selection']='Dedicated config provider alias for the finite executor; no alternate generative model and no inference on the FSA path.' if family=='openclaw' else 'Dedicated public ProviderProfile/ACP route, ordinary DeepSeek route selected again for the control. No core modification or alternate generative model.'
  save(run/'result.json',rec);print('EXECUTOR_DONE',unit,family,rec['passed'],flush=True)
  if not rec['passed']:raise RuntimeError('Executor implementation did not meet common contract; inspect rather than assume interface absence')
  return rec
 finally:fixture.close()
def main():
 from run_policy_fragments import main as check_policy_fragments
 check_policy_fragments()
 os.chdir(OLD);results=[]
 for unit in range(1,4):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(run_case(unit,family));save(R/'results/executor-routes.json',results)
 print('EXECUTOR_ROUTES_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
