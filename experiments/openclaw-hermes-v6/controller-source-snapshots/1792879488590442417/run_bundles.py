"""A fixed external-format matrix. Unsupported formats are distinguished from broken supported adapters."""
import hashlib,json,os,shutil,subprocess,time,uuid
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,command,save
from controlled import Plan
from run_state_ops import cli
from run_mcp_contracts import flatten
import mcp_contract_fixture as F
FORMATS={'agent':'plugin.json','claude':'.claude-plugin/plugin.json','codex':'.codex-plugin/plugin.json','cursor':'.cursor-plugin/plugin.json'}

def package(root,format,unit):
 root.mkdir(parents=True);manifest={'name':'evalbundle','version':'1.0.0','description':'Matched portable bundle'}
 if format=='agent':manifest['$schema']='https://agent-plugins.org/schemas/1.0.0/plugin.schema.json'
 save(root/FORMATS[format],manifest);server={'command':'/usr/bin/python3','args':['/workspace/bundle/mcp_fixture.py']}
 if format=='agent':mcp={'$schema':'https://agent-plugins.org/schemas/1.0.0/mcp.schema.json','mcpServers':{'portable':{'type':'stdio',**server}}};name='mcp.json'
 else:mcp={'mcpServers':{'portable':server}};name='.mcp.json'
 save(root/name,mcp);shutil.copy(Path(F.__file__),root/'mcp_fixture.py');skill=root/'skills/evalportable';skill.mkdir(parents=True);marker=f'PORTABLE_SKILL_CANARY_U{unit}';(skill/'SKILL.md').write_text('---\nname: evalportable\ndescription: '+marker+'; normalize Unicode using the installed portable MCP tool.\n---\nPreserve Unicode exactly; do not send data to external services.\n');return marker

def skills(names,body):return [('skills_list',{})] if 'skills_list' in names else []
def echo(names,body):
 name=next((n for n in names if n.endswith('unicode_echo')),None);return [(name,{'text':F.UNICODE})] if name else []

def execute(run,family,label):
 trace=run/label;trace.mkdir();(run/'workspace/mcp-truth.jsonl').unlink(missing_ok=True);fixture=Plan(trace,family,[skills,echo] if family=='hermes' else [echo]);cmd=cli(family,['agent','--local','--agent','main','--session-id',uuid.uuid4().hex,'--message',(run/'workspace/PROMPT.md').read_text(),'--json','--timeout','60']) if family=='openclaw' else command(family)
 # All native tools are allowed here; search is disabled to make exposure observable without another model.
 try:
  with (trace/'stdout.jsonl').open('w') as out,(trace/'stderr.log').open('w') as err:p=subprocess.run(sandbox(run/'state',run/'workspace',family,cmd,fixture.socket_dir),stdout=out,stderr=err,timeout=100)
  requests=fixture.calls;text='\n'.join(flatten([m for c in requests for m in c['request'].get('messages',[])]));returned='\n'.join(flatten([m for c in requests for m in c['request'].get('messages',[]) if m.get('role')=='tool']));tools=[x['function']['name'] for c in requests for x in c['request'].get('tools',[])];truth=run/'workspace/mcp-truth.jsonl';rpc=[json.loads(line) for line in truth.read_text().splitlines()] if truth.exists() else [];received=any(x['request'].get('method')=='tools/call' and x['request'].get('params',{}).get('name')=='unicode_echo' and x['request'].get('params',{}).get('arguments',{}).get('text')==F.UNICODE for x in rpc);save(trace/'native-recipient-truth.json',rpc);rec=dict(exit_code=p.returncode,unicode_tool_advertised=any(n.endswith('unicode_echo') for n in tools),unicode_preserved=F.UNICODE in returned and received,recipient_called=received,skill_registered='PORTABLE_SKILL_CANARY_' in text,main_requests=sum(x['main'] for x in requests));save(trace/'result.json',rec);return rec
 finally:fixture.close()

def run_case(unit,format,family):
 run=R/'runs-bundles'/format/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial format attempt retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');work=run/'workspace';work.mkdir();(work/'PROMPT.md').write_text('Inspect the installed portable bundle and run its controlled Unicode tool, if advertised.');bundle=work/'bundle';marker=package(bundle,format,unit)
 cfgpath=run/'state'/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');c=json.loads(cfgpath.read_text())
 if family=='openclaw':c['tools']={'toolSearch':False,'alsoAllow':['group:plugins']}
 else:c['plugins']={'enabled':['evalbundle']};c['tools']={'tool_search':{'enabled':'off'}};shutil.copytree(bundle,run/'state/hermes/plugins/evalbundle')
 save(cfgpath,c);print('BUNDLE_START',format,unit,family,flush=True)
 if family=='openclaw':
  cmd=sandbox(run/'state',work,family,cli(family,['plugins','install','--force','--accept-capabilities','--link','/workspace/bundle']));p=subprocess.run(cmd,capture_output=True,text=True,timeout=100);save(run/'native-install.json',dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
  if p.returncode:raise RuntimeError('A documented supported bundle did not install; inspect manifest/installer before grading')
  c=json.loads(cfgpath.read_text());c.setdefault('tools',{}).setdefault('alsoAllow',[]).append('portable__unicode_echo');save(cfgpath,c)
 primary=execute(run,family,'original-format');rec=dict(unit=unit,family=family,format=format,primary=primary,source_contract='OpenClaw docs/plugins/bundles.md lists all4; Hermes hermes_cli/agent_plugins.py requires root plugin.json schema1.0.0 or native plugin.yaml. Format breadth is distinct from underlying tool/skill capability.',supported_as_declared=family=='openclaw' or format=='agent')
 if not rec['supported_as_declared'] and not primary['unicode_tool_advertised']:
  rec['status']='unsupported_with_source_confirmation';old=run/'state/hermes/plugins/evalbundle';shutil.rmtree(old);shutil.copytree(bundle,old);save(old/'plugin.json',{'$schema':'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json','name':'evalbundle','version':'1.0.0','description':'Converted standard manifest; program and skill unchanged'});save(old/'mcp.json',{'$schema':'https://agent-plugins.org/schemas/1.0.0/mcp.schema.json','mcpServers':{'portable':{'type':'stdio','command':'/usr/bin/python3','args':['/workspace/bundle/mcp_fixture.py']}}});rec['conversion_control']=execute(run,family,'converted-to-agent-standard');rec['conversion_core_changes']=False;rec['conversion_steps']=['add root standard plugin.json','translate MCP manifest shape to mcp.json'];rec['baseline_credit']=False
 else:
  rec['status']='accepted' if primary['unicode_tool_advertised'] and primary['unicode_preserved'] and primary['skill_registered'] else 'needs_adapter_review'
 save(run/'result.json',rec);print('BUNDLE_DONE',format,unit,family,rec['status'],flush=True)
 if rec['supported_as_declared'] and rec['status']!='accepted':raise RuntimeError('Supported format needs adapter review before expansion')
 return rec

def main():
 os.chdir(OLD);results=[]
 for unit in range(1,4):
  for format in FORMATS:
   for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(run_case(unit,format,family));save(R/'results/bundles.json',results)
 print('BUNDLE_CONTRACTS_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
