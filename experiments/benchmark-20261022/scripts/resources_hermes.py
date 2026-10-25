import os,sys,json,hashlib,time,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1]; W=R/'runtime/extended-resources/hermes'; W.mkdir(parents=True,exist_ok=True)
os.environ['HERMES_HOME']=str(W/'home');os.environ['HERMES_RUNTIME_DIR']=str(W/'runtime');sys.path.insert(0,str(R/'sources/hermes'))
Path(os.environ['HERMES_HOME']).mkdir(exist_ok=True)
(Path(os.environ['HERMES_HOME'])/'config.yaml').write_text('skills:\n  external_dirs: []\n  disabled: []\n')
from tools import skills_tool as st,skill_manager_tool as sm,memory_tool as mt
from tools.memory_tool_store import MemoryStore
from tools.checkpoint_manager import CheckpointManager
out={'12':[],'14':[],'24':[]}; detail={}
if '--skills-only' in sys.argv:
 try:out=json.loads((R/'raw/extended-resources/hermes.json').read_text());out['12']=[]
 except FileNotFoundError:pass
def case(row,name,fn):
 try:
  ok,meta=fn();out[str(row)].append({'name':name,'passed':bool(ok),'detail':meta})
 except Exception as e:out[str(row)].append({'name':name,'passed':False,'error':repr(e)})
def skillcontent(name,n):return f'---\nname: {name}\ndescription: Synthetic lifecycle test {n}\n---\n# Synthetic\nVersion value {n}.\n'
# Use native manager mutation helpers beneath approval dispatch; fixtures are pre-authorized local test artifacts.
for i in range(3):
 name=f'resources-lifecycle-{i}'
 def create():
  r=sm._create_skill(name,skillcontent(name,1));return r.get('success') and any(x['name']==name for x in st.find_all_skills()),r
 case(12,f'create_discover_{i}',create)
 def read():
  r=json.loads(st.skill_view(name,preprocess=False));return r.get('success') and 'Version value 1.' in r.get('content',''),r
 case(12,f'read_{i}',read)
 def update():
  r=sm._edit_skill(name,skillcontent(name,2));v=json.loads(st.skill_view(name,preprocess=False));return r.get('success') and 'Version value 2.' in v.get('content',''),r
 case(12,f'update_read_{i}',update)
 def delete():
  r=sm._delete_skill(name);st.clear_skills_cache();return r.get('success') and not any(x['name']==name for x in st.find_all_skills()),r
 def disable():
  from hermes_cli.skills_config import save_disabled_skills
  from hermes_cli.config import load_config
  save_disabled_skills(load_config(),{name});st.clear_skills_cache();return not any(x['name']==name for x in st.find_all_skills()),{'disabled':name}
 case(12,f'disable_{i}',disable)
 def enable():
  from hermes_cli.skills_config import save_disabled_skills
  from hermes_cli.config import load_config
  save_disabled_skills(load_config(),set());st.clear_skills_cache();return any(x['name']==name for x in st.find_all_skills()),{'enabled':name}
 case(12,f'enable_{i}',enable)
 case(12,f'delete_discover_{i}',delete)
if '--skills-only' in sys.argv:
 (R/'raw/extended-resources/hermes.json').write_text(json.dumps(out,indent=2));print(json.dumps({'12':{'passed':sum(x['passed']for x in out['12']),'total':len(out['12'])}}));raise SystemExit(0)
for i in range(4):
 target='memory' if i%2==0 else 'user';v=f'Experiment fact {i}: code Q{i}A.';u=f'Experiment fact {i}: code Q{i}B.'
 def add():
  s=MemoryStore();s.load_from_disk();r=s.add(target,v);t=MemoryStore();t.load_from_disk();e=t.memory_entries if target=='memory' else t.user_entries;return r.get('success') and v in e,r
 case(14,f'add_fresh_store_{i}',add)
 def update():
  s=MemoryStore();s.load_from_disk();r=s.replace(target,v,u);t=MemoryStore();t.load_from_disk();e=t.memory_entries if target=='memory' else t.user_entries;return r.get('success') and u in e and v not in e,r
 case(14,f'update_fresh_store_{i}',update)
 def delete():
  s=MemoryStore();s.load_from_disk();r=s.remove(target,u);t=MemoryStore();t.load_from_disk();e=t.memory_entries if target=='memory' else t.user_entries;return r.get('success') and u not in e,r
 case(14,f'delete_fresh_store_{i}',delete)
def hashes(w):return {str(p.relative_to(w)):hashlib.sha256(p.read_bytes()).hexdigest() for p in w.rglob('*') if p.is_file()}
for i in range(10):
 def snapshot():
  w=W/f'project-{i}';shutil.rmtree(w,ignore_errors=True);w.mkdir(exist_ok=True);(w/'nested').mkdir(exist_ok=True)
  (w/'original.txt').write_text('unchanged fact '+str(i));(w/'nested/data.bin').write_bytes(bytes(range(256))*4);(w/'remove.txt').write_text('restore deleted')
  expected=hashes(w);m=CheckpointManager(enabled=True,max_snapshots=20);created=m.ensure_checkpoint(str(w),'synthetic-baseline');c=m.list_checkpoints(str(w))
  if not c:return False,{'created':created,'error':'no checkpoint'}
  (w/'original.txt').write_text('changed');(w/'remove.txt').unlink();(w/'new.txt').write_text('post checkpoint addition')
  start=time.perf_counter();res=m.restore(str(w),c[0]['hash'],safe=False);ms=(time.perf_counter()-start)*1000;actual=hashes(w)
  return res.get('success') and all(actual.get(k)==v for k,v in expected.items()),{'created':created,'restore':res,'expected':expected,'actual':actual,'post_checkpoint_new_files_preserved':[p for p in actual if p not in expected],'duration_ms':ms}
 case(24,f'modify_delete_add_restore_{i}',snapshot)
p=R/'raw/extended-resources/hermes.json';p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(out,indent=2));print(json.dumps({k:{'passed':sum(x['passed'] for x in v),'total':len(v)}for k,v in out.items()}))
