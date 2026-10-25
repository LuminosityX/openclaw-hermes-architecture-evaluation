"""K06: native cross-agent setup import, configured official capabilities.
Scope is promised model/MCP/skill/memory setup, not live foreign execution receipts.
Both vendors explicitly keep some foreign runtime/session data archive-only.
"""
import json,os,shutil,subprocess,time,hashlib
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,command,save,read_config
from controlled import Plan
from gateway import Gateway
from run_state_ops import cli
ADDON=R/'runtime/hermes-agent-importers'
SERVER=r'''
import sys,json,os
from pathlib import Path
for line in sys.stdin:
 r=json.loads(line);m=r.get('method');out={}
 if m=='initialize':out={'protocolVersion':r.get('params',{}).get('protocolVersion','2025-03-26'),'capabilities':{'tools':{}},'serverInfo':{'name':'import-compat-server','version':'1.0'}}
 elif m=='tools/list':out={'tools':[{'name':'identity','description':'Read-only imported server identity','inputSchema':{'type':'object','properties':{}},'annotations':{'readOnlyHint':True}}]}
 elif m=='tools/call':
  value='IMPORTED_MCP:'+os.environ.get('IMPORT_GREETING','MISSING');Path('/workspace/imported-mcp-received.json').write_text(json.dumps({'greeting':os.environ.get('IMPORT_GREETING'),'method':m}));out={'content':[{'type':'text','text':value}]}
 if 'id' in r:print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':out}),flush=True)
'''

def invoke(run,family,args,label,mounts=()):
 result=subprocess.run(sandbox(run/'state',run/'workspace',family,cli(family,args),extra_mounts=mounts),capture_output=True,text=True,timeout=180,stdin=subprocess.DEVNULL);row=dict(exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr);save(run/(label+'.json'),row)
 if result.returncode:raise RuntimeError('Native setup import operation failed: '+label)
 return row

def source_fixture(run,unit,target_family):
 source=run/'source-input';source.mkdir();work=source/'workspace';work.mkdir();skill='ci-u'+str(unit);description='IMPORT_SKILL_U'+str(unit);greeting='NATIVE_IMPORT_U'+str(unit)+'_中文';memory='SOURCE_MEMORY_U'+str(unit)
 package=source/'skills'/skill;package.mkdir(parents=True);(package/'SKILL.md').write_text('---\nname: '+skill+'\ndescription: '+description+'\n---\n'+description+' body.\nUse the imported identity server only for this synthetic example.\n')
 server={'command':'/usr/bin/python3','args':['/workspace/import_mcp_server.py'],'env':{'IMPORT_GREETING':greeting}}
 if target_family=='openclaw':
  cfg={'model':{'default':'deepseek-flash','provider':'deepseek','base_url':'http://127.0.0.1:18080/ds/v1'},'mcp_servers':{'imported':{**server,'trust':'full','lazy':False}}};save(source/'config.yaml',cfg);(source/'memories').mkdir();(source/'memories/MEMORY.md').write_text(memory+'\n');(source/'SOUL.md').write_text('Synthetic imported persona '+str(unit)+'\n')
 else:
  cfg={'agents':{'defaults':{'workspace':'/import-source/workspace','model':{'primary':'deepseek/deepseek-flash'}}},'models':{'providers':{'deepseek':{'baseUrl':'http://127.0.0.1:18080/ds/v1','api':'openai-completions','apiKey':'synthetic-source-key','models':[{'id':'deepseek-flash','name':'DeepSeek Flash','reasoning':True,'contextWindow':1000000,'maxTokens':65536}]}}},'mcp':{'servers':{'imported':{**server,'transport':'stdio','enabled':True}}}};save(source/'openclaw.json',cfg);(work/'MEMORY.md').write_text(memory+'\n');(work/'SOUL.md').write_text('Synthetic imported persona '+str(unit)+'\n')
 return source,dict(skill=skill,description=description,greeting=greeting,memory=memory)

def one(unit,family):
 run=R/'runs-import-compat'/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial setup-import preflight retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');work=run/'workspace';work.mkdir();(work/'PROMPT.md').write_text('Controlled native setup import verification.');(work/'import_mcp_server.py').write_text(SERVER);source,expected=source_fixture(run,unit,family);mounts=[(source,'/import-source',True)];p=run/'state'/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');cfg=read_config(p)
 if family=='openclaw':cfg['tools']={'profile':'full','toolSearch':False,'exec':{'mode':'full'}};cfg['cron']={'enabled':False}
 else:cfg['approvals']={'mode':'off','single_query_mode':'approve','unattended_mode':'approve'};cfg['tools']={'tool_search':{'enabled':'off'}}
 save(p,cfg);save(run/'source-input-manifest.json',{str(f.relative_to(source)):hashlib.sha256(f.read_bytes()).hexdigest() for f in source.rglob('*') if f.is_file()});print('SETUP_IMPORT_START',unit,family,flush=True)
 if family=='hermes':
  if not(ADDON/'PREPARED.json').exists():raise RuntimeError('Official catalog importer source is not pinned/prepared')
  plugin=run/'state/hermes/plugins/agent-importers';shutil.copytree(ADDON,plugin,ignore=shutil.ignore_patterns('PREPARED.json','__pycache__'))
  from native_hermes_mutation_support import prepare
  prepare(run);invoke(run,family,['plugins','enable','agent-importers'],'official-importer-enable')
  applied=invoke(run,family,['import-agent','openclaw','--source','/import-source','--workspace-target','/workspace','--migrate-secrets','--overwrite','--yes'],'native-import-apply',mounts)
 else:applied=invoke(run,family,['migrate','apply','hermes','--from','/import-source','--overwrite','--include-secrets','--yes','--json'],'native-import-apply',mounts)
 listed=invoke(run,family,['skills','list'],'native-imported-skill-discovery',mounts)
 roots=[work,run/'state/hermes/skills'] if family=='hermes' else [work,run/'state/openclaw/skills'];skill_files=[]
 for root in roots:
  if root.exists():
   for file in root.rglob('SKILL.md'):
    if expected['description'] in file.read_text(errors='replace'):skill_files.append(str(file.relative_to(run)))
 def identity(names,body):
  name=next((n for n in names if 'imported' in n and n.endswith('identity')),None)
  if not name:raise RuntimeError('Imported native MCP tool was not actually advertised')
  return [(name,{})]
 fixture=Plan(run,family,[identity]);gateway=Gateway(run,family,fixture,allow_disk_warning=True)
 try:
  gateway.start();response=gateway.chat('Verify the imported server identity using the supplied native tool.','setup-import-u'+str(unit),timeout=60);gateway.stop();results=[m for c in fixture.calls if c['main'] for m in c['request'].get('messages',[]) if m.get('role')=='tool'];tool_seen='IMPORTED_MCP:'+expected['greeting'] in json.dumps(results,ensure_ascii=False);received=work/'imported-mcp-received.json';truth=json.loads(received.read_text()) if received.exists() else {};cfg=read_config(p);row=dict(unit=unit,family=family,native_import_exit=applied['exit_code'],native_mcp_effect_and_projection=tool_seen and truth.get('greeting')==expected['greeting'],native_skill_discovered=expected['skill'] in listed['stdout'] or expected['description'] in listed['stdout'],imported_skill_material=skill_files,memory_source=expected['memory'],response_status=response.get('status'),official_importer='bundled Hermes migration provider' if family=='openclaw' else 'official catalog agent-importers1.1.0@b5932f1b',real_model=False,scope='Only documented setup surfaces: imported native MCP actually invokes its recipient and preserves supplied literal env; skill material and native discovery checked. Operator explicitly authorizes all synthetic literal values. No OAuth/live foreign session or running-task receipt activation is asserted. Official optional Hermes importer is configured, not treated absent because it is not core-default.')
  row['passed']=row['native_mcp_effect_and_projection'] and row['native_skill_discovered'] and bool(skill_files) and row['response_status']==200;save(run/'result.json',row);print('SETUP_IMPORT_DONE',unit,family,row['passed'],flush=True)
  if not row['passed']:raise RuntimeError('Setup-import behavior needs native format/permission adjudication before expansion')
  if family=='hermes':
   from archive_completed_private_dependencies import one as retain_completed_dependencies
   row['dependency_archive']=retain_completed_dependencies(run);save(run/'result.json',row)
  return row
 finally:gateway.stop();fixture.close()

def main():
 from stage_provenance import snapshot
 snapshot('configured-native-setup-imports-substage')
 os.chdir(OLD);rows=[]
 for unit in range(1,4):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):rows.append(one(unit,family));save(R/'results/setup-imports.json',rows)
 print('SETUP_IMPORTS_COMPLETE',len(rows),flush=True)
if __name__=='__main__':main()
