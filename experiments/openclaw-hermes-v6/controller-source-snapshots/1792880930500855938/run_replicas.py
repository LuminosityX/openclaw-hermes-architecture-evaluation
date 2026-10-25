"""E06b common minimum: complete official Gateway replicas on two isolated Linux nodes.
Sessions remain node-affine; this is not transparent session migration or an invented native cluster.
Native specialized worker orchestration remains a separately documented additional capability.
"""
import concurrent.futures,hashlib,json,os,time
from pathlib import Path
from runtime import R,OLD,configuration,save
from controlled import Plan
from gateway import Gateway
class Peer(Plan):
 def handler(self):
  Base=super().handler()
  class H(Base):
   def do_POST(self):time.sleep(.25);return super().do_POST()
  return H

def route(names,body):
 messages=body.get('messages',[]);index=max((i for i,m in enumerate(messages) if m.get('role')=='user'),default=0);text=str(messages[index].get('content',''));current=messages[index+1:]
 if any(m.get('role')=='tool' for m in current):return []
 if 'NODE_PROOF:' not in text:raise RuntimeError('Replica proof task missing')
 token=text.split('NODE_PROOF:',1)[1].split()[0];name=next((n for n in names if n in ['write','write_file']),None)
 if not name:raise RuntimeError('Complete native replica did not expose file delivery capability')
 return [(name,{'path':'/workspace/placement-proof-'+token+'.txt','content':token})]

def one(unit,family):
 root=R/'runs-replicas'/f'u{unit}'/family
 if (root/'result.json').exists():return json.loads((root/'result.json').read_text())
 if root.exists():raise RuntimeError('Partial topology retained '+str(root))
 root.mkdir(parents=True);gateways=[];fixtures=[]
 for node in ['a','b']:
  run=root/node;run.mkdir();configuration(family,run/'state');(run/'workspace').mkdir();(run/'workspace/PROMPT.md').write_text('Independent node fixture. No shared user state.');fixture=Peer(run,family,router=route);gateway=Gateway(run,family,fixture,concurrency=1);fixtures.append(fixture);gateways.append(gateway)
 def task(node,tag,session=None):
  g=gateways[node];token=f'U{unit}_{tag}';begin=len(fixtures[node].calls);reply=g.chat('NODE_PROOF:'+token+' Deliver the exact token to a new file placement-proof-'+token+'.txt using your native write tool.',session or tag,timeout=45);path=g.run/'workspace'/('placement-proof-'+token+'.txt');correct=reply.get('status')==200 and path.exists() and path.read_text()==token;first=next((x['request'] for x in fixtures[node].calls[begin:] if x['main']),{});return dict(node=node,tag=tag,correct=correct,response=reply,first_request=first)
 print('REPLICAS_START',unit,family,flush=True)
 try:
  for g in gateways:g.start()
  warm=[task(0,'stable-a','stable-a'),task(1,'stable-b','stable-b')]
  if not all(x['correct'] for x in warm):raise RuntimeError('Both full native nodes must pass actual model/tool/persistence warmup')
  measurements=[]
  for copies in ([1,2] if unit%2 else [2,1]):
   start=time.monotonic()
   def lane(node):return [task(node,f'{copies}-copies-node{node}-job{n}') for n in range(4//copies)]
   with concurrent.futures.ThreadPoolExecutor(max_workers=copies) as pool:groups=list(pool.map(lane,range(copies)))
   elapsed=time.monotonic()-start;rows=[x for group in groups for x in group];measurements.append(dict(copies=copies,seconds=elapsed,correct=sum(x['correct'] for x in rows),total=len(rows),throughput=sum(x['correct'] for x in rows)/elapsed,tasks=rows))
  gateways[0].stop();survivor=task(1,'while-a-offline');gateways[0].start();resumed=task(0,'after-a-restart','stable-a');old_visible='NODE_PROOF:U'+str(unit)+'_stable-a' in json.dumps(resumed['first_request'].get('messages',[]));rec=dict(unit=unit,family=family,full_nodes=2,warmup=[{k:v for k,v in x.items() if k!='first_request'} for x in warm],measurements=measurements,other_node_healthy_during_outage=survivor['correct'],restarted_same_node_ready=resumed['correct'],same_node_prior_history_retained=old_visible,node_storage_distinct=gateways[0].run!=gateways[1].run,passed=all(x['correct']==x['total'] for x in measurements) and survivor['correct'] and resumed['correct'] and old_visible,scope='Independent whole Gateway replicas with distinct namespaces/state/workspaces and node-affine sessions. External load generator chooses replicas; no native scheduler, shared-state cluster or automatic cross-node continuation is claimed. Single-node multiplexing is measured separately in E06a.')
  save(root/'result.json',rec);print('REPLICAS_DONE',unit,family,rec['passed'],flush=True)
  if not rec['passed']:raise RuntimeError('Topology or persistence contract needs adjudication')
  return rec
 finally:
  for g in gateways:g.stop()
  for f in fixtures:f.close()
def main():
 os.chdir(OLD);results=[]
 for unit in range(1,4):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(one(unit,family));save(R/'results/replicas.json',results)
 print('FULL_REPLICA_TOPOLOGIES_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
