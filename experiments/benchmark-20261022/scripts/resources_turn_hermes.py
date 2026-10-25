import sys,os,json,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];W=R/'runtime/extended-resources/hermes-turns';W.mkdir(parents=True,exist_ok=True);os.environ['HERMES_HOME']=str(W);os.environ['HERMES_RUNTIME_DIR']=str(W/'runtime');(W/'config.yaml').write_text('model:\n  context_length: 128000\nbackground_review:\n  enabled: false\nterminal:\n  backend: local\n');sys.path.insert(0,str(R/'sources/hermes'));from run_agent import AIAgent
hz=os.sysconf('SC_CLK_TCK')
def proc():
 fields=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split();return dict(zip(['user','system','child_user','child_system'],[int(fields[k])for k in[11,12,13,14]]))
out=[]
for i in range(13):
 p=proc();start=time.perf_counter_ns();a=AIAgent(api_key='synthetic-local-fixture-key',base_url='http://127.0.0.1:38773/v1',provider='custom',api_mode='chat_completions',model='local-fixture',max_tokens=128,reasoning_config={'enabled':False,'effort':'none'},enabled_toolsets=[],quiet_mode=True,skip_context_files=True,skip_memory=True,skip_background_review=True,max_iterations=2,session_id=f'hermes-minimal-turn-{i}',cwd=str(W));tool_count=len(a.tools)
 try:r=a.run_conversation('CASE:unicode 中文测试🐱')
 finally:a.close()
 end=time.perf_counter_ns();q=proc();valid=json.loads(r['final_response']).get('valid')is True and tool_count==0;rec={'framework':'hermes','sample':i-3,'warmup':i<3,'cpu_ms':(sum(q.values())-sum(p.values()))*1000/hz,'wall_ms':(end-start)/1e6,'cpu_before':p,'cpu_after':q,'correct':valid,'tool_count':tool_count,'final_response':r['final_response']};out.append(rec);(R/'raw/extended-resources/turn-hermes.json').write_text(json.dumps({'clock_ticks':hz,'scope':'Native AIAgent construct, complete minimal text turn and close; imports excluded, three warmups and ten measured turns; no selected tools; configured local compatible endpoint.','samples':out},indent=2));print(json.dumps({'sample':i-3,'cpu_ms':rec['cpu_ms'],'correct':valid}),flush=True)
 if not valid:raise RuntimeError('native turn failed')
