import os,sys,json,gc,secrets,tracemalloc,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];os.environ['HERMES_HOME']=str(R/('runtime/extended-resources/memory-hermes-'+(sys.argv[2]if len(sys.argv)>2 else'0')));Path(os.environ['HERMES_HOME']).mkdir(exist_ok=True);(Path(os.environ['HERMES_HOME'])/'config.yaml').write_text('model:\n  context_length: 128000\nbackground_review:\n  enabled: false\nterminal:\n  backend: local\n');sys.path.insert(0,str(R/'sources/hermes'))
from run_agent import AIAgent
count=int(sys.argv[1])if len(sys.argv)>1 else 100;sample=int(sys.argv[2])if len(sys.argv)>2 else 0

def make():return AIAgent(api_key='synthetic-local-fixture-key',base_url='http://127.0.0.1:38773/v1',provider='custom',api_mode='chat_completions',model='local-fixture',enabled_toolsets=[],quiet_mode=True,skip_context_files=True,skip_memory=True,skip_background_review=True,max_iterations=2,session_id='memory-'+secrets.token_hex(12),prefill_messages=[{'role':'user','content':'HISTORY:'+secrets.token_hex(8192)}],cwd=str(R))
def mem():
 gc.collect();gc.collect();d={}
 for line in Path('/proc/self/smaps_rollup').read_text().splitlines():
  p=line.split()
  if p[0].rstrip(':')in['Rss','Pss','Private_Clean','Private_Dirty']:d[p[0].rstrip(':')]=int(p[1])*1024
 return {'rss':d['Rss'],'pss':d['Pss'],'private':d['Private_Clean']+d['Private_Dirty'],'managed_heap':tracemalloc.get_traced_memory()[0]}
w=make();v=w.run_conversation('CASE:unicode 中文测试🐱');assert '"valid": true'in v['final_response'],v['final_response'];w.close();del w,v
before=mem();cpu_start=time.process_time_ns();held=[make()for _ in range(count)];cpu_ms=(time.process_time_ns()-cpu_start)/1e6;distinct=len({a.prefill_messages[0]['content']for a in held})==count;after=mem();v=held[-1].run_conversation('CASE:unicode 中文测试🐱');working='"valid": true'in v['final_response']
r={'creation_cpu_ms':cpu_ms,'framework':'hermes','count':count,'sample':sample,'before':before,'after':after,'delta_rss_bytes':after['rss']-before['rss'],'delta_private_bytes':after['private']-before['private'],'delta_pss_bytes':after['pss']-before['pss'],'unique_16kib_histories':distinct,'functional':working,'tool_counts':sorted(set(len(a.tools)for a in held)),'scope':'Warm AIAgent idle conversation-controller allocation, native custom provider, no selected tools, no memory/context files or gateway. Baseline excludes shared imports and provider warmup.'}
(R/f'raw/extended-resources/memory-hermes-{count}-{sample}.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
for a in held:a.close()
