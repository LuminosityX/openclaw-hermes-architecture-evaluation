"""Read-only provenance: native asset access versus retained workspace program access."""
import hashlib,json,re
from runtime import R,save

def one(root,episode):
 rec=json.loads((root/f'episode-{episode}/result.json').read_text());calls={};results={}
 for i in range(rec['first_global_call'],rec['last_global_call']+1):
  path=root/f'api-request-{i:03}.json'
  if not path.exists():continue
  body=json.loads(path.read_text())
  for m in body.get('messages',[]):
   if m.get('role')=='tool':results[m.get('tool_call_id')]=m.get('content','')
   for call in m.get('tool_calls',[]):calls[call.get('id')]=call.get('function',{})
 rows=[]
 for key,fn in calls.items():
  args=fn.get('arguments','');name=fn.get('name','');text=name+' '+args
  native_path=any(x in args for x in ['workshop-skills','/memories/','/hermes/skills/'])
  direct_read=name in ['skill_view','skills_read','memory_get','memory_search']
  if name=='tool_call':
   try:
    payload=json.loads(args);named=str(payload.get('id') or payload.get('name') or '')
    direct_read=any(named.endswith(x) for x in ['skills_read','memory_get','memory_search'])
   except ValueError:pass
  path_read=native_path and (name in ['read','read_file'] or name in ['exec','terminal'] and bool(re.search(r'\b(cat|head|tail|sed|rg)\b|\.read_text\(|\.read_bytes\(',args)))
  kind='native_asset' if direct_read or path_read else 'workspace_program' if any(x in text for x in ['reconcile_data.py','sync_worker.py']) else None
  if kind:
   content=results.get(key);serialized=json.dumps(content,ensure_ascii=False);rows.append(dict(tool_call_id=key,native_tool=name,args=args,kind=kind,result_observed=key in results,result_sha256=hashlib.sha256(serialized.encode()).hexdigest() if content is not None else None,result_chars=len(serialized),returned_text_has_possible_error_phrase=bool(re.search(r'No such file|not found|permission denied|not available',serialized,re.I))))
 return dict(unit=rec['unit'],family=rec['family'],episode=episode,task=rec['task'],session_key=rec['session_key'],same_service_namespace_pid=rec['same_service_namespace_pid'],passed=rec['passed'],native_asset_reads=[x for x in rows if x['kind']=='native_asset'],program_accesses=[x for x in rows if x['kind']=='workspace_program'],scope='Actual native assistant call IDs and returned tool messages within the completed episode request range. Workspace program use is separate from native memory/skill access. A successful read proves access, not a causal estimate of its benefit; no evaluator asset text is injected.')

def main():
 rows=[]
 for p in sorted((R/'runs-reuse').glob('u*/*/episode-*/result.json')):
  rows.append(one(p.parent.parent,int(p.parent.name.split('-')[1])))
 save(R/'results/reuse-asset-provenance.json',rows);print('REUSE_ASSET_PROVENANCE',len(rows),'episodes')
if __name__=='__main__':main()
