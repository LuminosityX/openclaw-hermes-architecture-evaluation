"""Official telemetry configurations, default conversation history, and receiver outage."""
import hashlib,json,os,subprocess,threading,time
from pathlib import Path
from runtime import R,OLD,configuration,sandbox,save
from controlled import Plan,shell
from gateway import Gateway
from run_state_ops import cli,db_inventory
from native_approval_workflow import approved_workflow
from inspect_native_state import decision_records
from prepare_observability import DEST
class Receiver(Plan):
 def __init__(self,*a,**kw):self.frames=[];self.down_until=0;super().__init__(*a,**kw)
 def handler(self):
  Base=super().handler();owner=self
  class H(Base):
   def do_POST(self):
    if not self.path.startswith('/otlp/'):return super().do_POST()
    body=self.rfile.read(int(self.headers.get('Content-Length',0)));accepted=time.monotonic()>=owner.down_until;folder=owner.run/'otlp-frames';folder.mkdir(exist_ok=True)
    with owner.lock:
     i=len(owner.frames)+1;name=f'frame-{i:04}.bin';(folder/name).write_bytes(body);meta=dict(path=self.path,at_ns=time.monotonic_ns(),accepted=accepted,body_file=name,content_type=self.headers.get('Content-Type'),content_encoding=self.headers.get('Content-Encoding'),sha256=hashlib.sha256(body).hexdigest());save(folder/f'frame-{i:04}.json',meta);owner.frames.append(meta)
    self.send_response(200 if accepted else 503);self.send_header('Content-Type','application/x-protobuf');self.send_header('Content-Length','0');self.end_headers()
  return H
TOML='''version = 1
[[components]]
kind = "observability"
enabled = true
[components.config]
version = 4
[components.config.opentelemetry]
enabled = true
[[components.config.opentelemetry.endpoints]]
type = "full"
endpoint = "http://127.0.0.1:18080/otlp/v1/traces"
transport = "http_binary"
service_name = "hermes-evaluation"
max_queue_size = 4096
max_export_batch_size = 512
scheduled_delay_millis = 500
[components.config.opentelemetry.logs]
enabled = true
[components.config.opentelemetry.metrics]
enabled = true
'''
def run_case(unit,mode,family):
 run=R/'runs-observability'/mode/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial observability attempt retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');work=run/'workspace';work.mkdir();token='AUDIT_CANARY_'+str(unit)+'_'+family;(work/'PROMPT.md').write_text('Controlled native event reconstruction '+token);(work/'step.py').write_text("from pathlib import Path\nimport sys,time\nwith Path('/workspace/effects.jsonl').open('a') as f:f.write(sys.argv[1]+'\\n')\nprint('NATIVE_RESULT_'+sys.argv[1])\n")
 p=run/'state'/('openclaw.json' if family=='openclaw' else 'hermes/config.yaml');c=json.loads(p.read_text());extra=[]
 if mode!='default':
  if family=='openclaw':
   c['plugins']={'allow':['diagnostics-otel'],'load':{'paths':['/addons/diagnostics-otel']},'entries':{'diagnostics-otel':{'enabled':True}}};c['logging']={'audit':{'enabled':True,'executionIdentity':True,'messages':'all'}};c['diagnostics']={'enabled':True,'otel':{'enabled':True,'endpoint':'http://127.0.0.1:18080/otlp','protocol':'http/protobuf','serviceName':'openclaw-evaluation','traces':True,'metrics':True,'logs':True,'sampleRate':1,'flushIntervalMs':500}};extra=[(DEST,'/addons/diagnostics-otel',True)]
  else:
   c['monitoring']={'gateway_health_export':{'enabled':True},'export':{'otlp':{'enabled':True,'endpoint':'http://127.0.0.1:18080/otlp/v1/traces'}}};c.setdefault('telemetry',{}).setdefault('shared_metrics',{}).update(enabled=True,send=False);(run/'state/hermes/relay-plugins.toml').write_text(TOML)
 if family=='openclaw':c.setdefault('tools',{})['exec']={'mode':'ask'}
 else:c['approvals']={'mode':'manual','single_query_mode':'deny','unattended_mode':'deny','timeout':90}
 steps=[]
 for value in ['first','second','SHOULD_BE_DENIED']:
  payload="from pathlib import Path; p=Path('/workspace/effects.jsonl'); p.open('a').write("+repr(value+'\n')+"); print("+repr('NATIVE_RESULT_'+value)+")"
  import shlex
  steps.append(shell('python3 -c '+shlex.quote(payload)))
 save(p,c);fixture=Receiver(run,family,steps,fault='503' if unit%2==0 else None);gateway=Gateway(run,family,fixture)
 if extra:
  original=gateway.command;at=original.index('--');insert=[]
  for src,dst,ro in extra:insert+=['--ro-bind' if ro else '--bind',str(src),dst]
  gateway.command=original[:at]+insert+original[at:]
 if mode!='default' and family=='hermes':
  at=gateway.command.index('--');gateway.command=gateway.command[:at]+['--setenv','HERMES_NEMO_RELAY_PLUGINS_TOML','/state/hermes/relay-plugins.toml']+gateway.command[at:]
 if mode=='outage':fixture.down_until=time.monotonic()+12
 print('OBSERVE_START',mode,unit,family,flush=True);begin=time.monotonic()
 try:
  # Native plugin installation/provenance is required before OpenClaw exporter activation.
  if mode!='default' and family=='openclaw':
   cmd=sandbox(run/'state',work,family,cli(family,['plugins','install','--force','--accept-capabilities','--link','/addons/diagnostics-otel']),fixture.socket_dir,extra);p=subprocess.run(cmd,capture_output=True,text=True,timeout=120);save(run/'native-addon-install.json',dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
   if p.returncode:raise RuntimeError('Official exporter plugin failed to install')
  gateway.start()
  if mode=='outage':fixture.down_until=time.monotonic()+5
  result,approval_decisions=approved_workflow(gateway,'Execute the controlled observation workflow '+token,'observation-'+str(unit));save(run/'chat-response.json',result);time.sleep(6 if mode=='outage' else 2);gateway.stop();elapsed=time.monotonic()-begin
  approvals_native=decision_records(run/'state',[x['identity'] for x in approval_decisions]);save(run/'native-approval-decision-records.json',approvals_native)
  inventory=db_inventory(run/'state',token);save(run/'native-history-inventory.json',inventory)
  frames=run/'otlp-frames';frames.mkdir(exist_ok=True);decoder=Path(__file__).parent/'decode_otlp.py';decoder_state=R/'evidence/otlp-decoder-state';configuration('hermes',decoder_state)
  # Decode under the installed Python ABI and its official telemetry dependency environment.
  script='cd /runtime/hermes-source; task_activation="$(python3 -m pm.environments --format sh)" || exit; eval "$task_activation"; exec python /decoder.py';decode=sandbox(decoder_state,work,'hermes',['bash','-c',script],extra_mounts=[(decoder,'/decoder.py',True),(frames,'/frames',True)])
  p=subprocess.run(decode,capture_output=True,text=True,timeout=60);save(run/'decoder-result.json',dict(exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
  decoded=json.loads((work/'otlp-decoded.json').read_text()) if (work/'otlp-decoded.json').exists() else [];spans=[]
  for frame in decoded:
   if not frame.get('accepted'):continue
   for resource in frame.get('decoded',{}).get('resource_spans',[]):
    for scope in resource.get('scope_spans',[]):spans+=scope.get('spans',[])
  ids={x.get('span_id') for x in spans};effects=(work/'effects.jsonl').read_text().splitlines() if (work/'effects.jsonl').exists() else []
  rec=dict(unit=unit,family=family,mode=mode,seconds=elapsed,native_task_completed=result.get('status')==200 and effects==['first','second'],truth_effects=effects,truth_model_requests=sum(x['main'] for x in fixture.calls),truth_injected_failures=sum(bool(x.get('injected_status')) for x in fixture.calls),default_history_persisted=any(x.get('token_hits') for x in inventory),receiver_attempts=len(fixture.frames),receiver_accepted=sum(x['accepted'] for x in fixture.frames),decoded_frames=len(decoded),decoder_exit=p.returncode,span_names=sorted({x.get('name') for x in spans}),spans=spans,parent_ids_present=sum(x.get('parent_span_id') in ids for x in spans),scope='Official exporter profiles and native state; independent fixture/effect receipts are truth only, never counted as product telemetry.')
  rec.update(truth_approval_decisions=approval_decisions,native_approval_live_rows=approvals_native,approval_workload='Two actual allow-once decisions and one deny on matched inline interpreter calls; same workflow under default/configured/outage profiles. Native store and official exporter are measured separately; operator-client records are truth only.')
  save(run/'result.json',rec);print('OBSERVE_DONE',mode,unit,family,rec['native_task_completed'],len(spans),flush=True)
  if not rec['native_task_completed']:raise RuntimeError('Observation workload failed; inspect before expanding')
  if mode!='default' and not spans:raise RuntimeError('Official telemetry path did not produce decoded accepted spans; inspect setup')
  return rec
 finally:gateway.stop();fixture.close()
def main():
 from run_plugin_standard_resume import main as complete_original_plugin_resume
 complete_original_plugin_resume()
 os.chdir(OLD);results=[]
 for unit in range(1,7):
  for mode in ['default','configured','outage']:
   for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(run_case(unit,mode,family));save(R/'results/observability.json',results)
 print('OBSERVABILITY_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
