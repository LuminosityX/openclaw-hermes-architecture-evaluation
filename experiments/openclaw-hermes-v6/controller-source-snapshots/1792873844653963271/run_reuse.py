"""E13: native same-profile assets across three NEW gateway sessions, 6 profiles/product."""
import concurrent.futures,copy,hashlib,json,os,shutil,subprocess,threading,time
from decimal import Decimal
from pathlib import Path
from runtime import R,OLD,configuration,save
from gateway import Gateway
from services import Business,AuditedRelay
from resources import create,read,wrap
import evaluate as E
from audit_relay_unlimited import utc
from reuse_data_oracle import expected as data_expected
BUDGET={'lock':threading.Lock(),'spent':0.,'reserved':0.,'limit':None}
ORIGINAL_EXPECTED=E.expected_business
REFERENCE=Path('/root/output/oc-hermes-comparison-20261024-v5/evidence/data-checker-selftest/workspace/reconcile_data.py')
def business_expected(spec):
 expected,report,latest=ORIGINAL_EXPECTED(spec)
 if spec.get('net_fee'):
  fee=Decimal(spec['net_fee']);groups={}
  for key,row in latest.items():
   if row['status']=='void':continue
   expected[key]['net']=f"{max(Decimal(0),Decimal(expected[key]['net'])-fee):.2f}"
   g=groups.setdefault(row['currency'],[0,Decimal(0)]);g[0]+=1;g[1]+=Decimal(expected[key]['net'])
  report['by_currency']=[dict(currency=k,records=v[0],net=f'{v[1]:.2f}') for k,v in sorted(groups.items())]
  report['billing_digest']=hashlib.sha256(json.dumps(sorted(expected.values(),key=lambda x:x['id']),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 return expected,report,latest
E.expected_business=business_expected

def inputs(run,unit,episode,task):
 work=run/'workspace';work.mkdir(exist_ok=True);v=(unit+episode-2)%3+1;source=R/'fixtures'/f'{task}-v{v}'
 # Future inputs are introduced only now; retain agent-authored programs/assets in the same workspace.
 for name in ['output','eval_rerun','eval_changed','report.json','report-rerun.json']:
  p=work/name
  if p.is_dir():shutil.rmtree(p)
  elif p.exists():p.unlink()
 prompt=(source/'PROMPT.md').read_text()
 spec=None;tag=f'reuse-u{unit}-e{episode}'
 if task=='W3':
  destination=work/'sources';destination.mkdir(exist_ok=True)
  for child in destination.iterdir():
   if child.is_dir():shutil.rmtree(child)
   else:child.unlink()
  shutil.copytree(source/'sources',destination,dirs_exist_ok=True);rounding='ROUND_HALF_EVEN' if episode==3 else 'ROUND_HALF_UP'
  if episode==3:
   p=work/'sources/policy-2026.txt';p.write_text(p.read_text().replace('ROUND_HALF_UP','ROUND_HALF_EVEN'));prompt+='\n本轮政策已更新为ROUND_HALF_EVEN；必须以本轮sources的政策为准，纠正旧记忆/技能的规则，重新计算。'
  save(R/'private'/f'W3-v{tag}-expected.json',data_expected(work/'sources'))
 else:
  if not (work/'sync_worker.py').exists():shutil.copy(source/'sync_worker.py',work/'sync_worker.py')
  spec=json.loads((R/'private'/f'W4-v{v}-service.json').read_text())
  # New order identities across episodes prevent old answer reuse.
  prefix=f'u{unit}-e{episode}-'
  for row in spec['orders']:row['id']=prefix+row['id']
  spec['initial']={prefix+k:{**row,'id':prefix+k} for k,row in spec['initial'].items()}
  if episode==3:
   spec['net_fee']='0.01';prompt+='\n本轮规则更新：每个active订单的最终net在原gross-refund基础上再减固定服务费0.01，最低0；by_currency据新net汇总。请纠正旧记忆/技能，其他接口和规则不变。'
 if episode==1:prompt+='\n这是专门的一次训练演练。除完成并验证任务外，请使用本产品原生的记忆或技能机制保存可复用流程，明确输入可变、当前规则需重读；不要保存本批答案作为新批次答案。以后会在同一profile的新会话中处理新输入。可保留参数化程序资产，并说明保存位置。'
 else:prompt+='\n这是一个全新的会话和新批次。可自主利用同一profile已有的原生记忆、技能或可重用程序；必须核对本轮输入和规则，不要沿用旧答案。'
 if episode==3:prompt+='\n完成后请同步更新已保存的规则说明，避免后续误用旧规则。'
 (work/'PROMPT.md').write_text(prompt);return tag,spec

def quiet(relay,seconds=2,maximum=20):
 start=time.monotonic();last=relay.calls;since=start
 while time.monotonic()-start<maximum:
  if relay.calls!=last:last=relay.calls;since=time.monotonic()
  if len(relay.responses)>=relay.calls and time.monotonic()-since>=seconds:return
  time.sleep(.1)

def run_profile(unit,family):
 run=R/'runs-reuse'/f'u{unit}'/family
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial profile retained '+str(run))
 run.mkdir(parents=True);configuration(family,run/'state');task='W3' if unit<=3 else 'W4';results=[];group=create('reuse-'+family+'-'+str(unit)+'-'+str(time.time_ns()));tag,spec=inputs(run,unit,1,task)
 if family=='hermes':
  # The user authorizes these synthetic local business/asset tasks just as in
  # the formal CLI suite. A live API approval bridge otherwise turns inline
  # Python into a human wait even when unattended_mode is approve.
  cfgpath=run/'state/hermes/config.yaml';cfg=json.loads(cfgpath.read_text());cfg['approvals']={'mode':'off','single_query_mode':'approve','unattended_mode':'approve'};save(cfgpath,cfg)
 else:
  cfgpath=run/'state/openclaw.json';cfg=json.loads(cfgpath.read_text());cfg['agents']['defaults']['timeoutSeconds']=900;save(cfgpath,cfg)
 save(run/'task-authorization.json',dict(scope='Authorized synthetic local business and native reusable-asset workflow; no manual approval workload in E13.',openclaw='tools.exec.mode=full' if family=='openclaw' else None,hermes='approvals.mode=off; native unconditional floors remain' if family=='hermes' else None,proof='Same API inline-tool authorization configuration already passed native extension controls; no new paid preflight.'))
 business=Business(spec,run/'episode-1/business-truth.json') if spec else None
 if business:business.path.parent.mkdir(exist_ok=True)
 relay=AuditedRelay(run,family,BUDGET,inference_authorized=True,business=business)
 # One read-only DIRECTORY mount hides the initial per-file mounts. Keeping its inode lets new
 # episode files appear without a restart, while the agent cannot edit them. No future input is exposed.
 extra=[(run/'workspace/sources','/workspace/sources',True)] if task=='W3' else []
 gateway=Gateway(run,family,relay,extra_mounts=extra);gateway.command=wrap(group,gateway.command);profile_started=time.monotonic();gateway.start()
 save(run/'persistent-service.json',dict(namespace_process_pid=gateway.process.pid,started=utc(),episodes=3,constant_service=True,new_session_per_episode=True,readonly_input_directory=task=='W3',scope='Same running official Gateway and profile; new public inputs introduced just in time. No restart to refresh native asset discovery.'))
 try:
  for episode in range(1,4):
   if episode>1:
    tag,spec=inputs(run,unit,episode,task);business=Business(spec,run/f'episode-{episode}/business-truth.json') if spec else None;relay.business=business
   trace=run/f'episode-{episode}';trace.mkdir(exist_ok=True)
   if business:business.path.parent.mkdir(exist_ok=True)
   save(trace/'input-manifest.json',{str(p.relative_to(run/'workspace')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (run/'workspace').rglob('*') if p.is_file()});save(trace/'spec.json',spec)
   before=read(group);before_calls=relay.calls;before_responses=len(relay.responses);started=time.monotonic();failure=None;response={};session='reuse-'+tag;pool=concurrent.futures.ThreadPoolExecutor(max_workers=1);future=pool.submit(gateway.chat,(run/'workspace/PROMPT.md').read_text(),session,930)
   print('REUSE_START',unit,family,episode,task,flush=True);last=0
   while not future.done():
    elapsed=time.monotonic()-started
    if elapsed-last>=30:print('REUSE_ACTIVE',unit,family,episode,round(elapsed),relay.calls-before_calls,flush=True);last=elapsed
    if elapsed>900 or relay.violations or relay.calls-before_calls>128:
     failure='timeout' if elapsed>900 else 'fixed_model_policy' if relay.violations else 'request_ceiling';gateway.stop();break
    time.sleep(1)
   try:response=future.result(timeout=20)
   except Exception as ex:response={'error':type(ex).__name__}
   pool.shutdown(wait=False,cancel_futures=True);delivery_seconds=time.monotonic()-started
   # Acceptance is evaluated at delivery, before any quiet grace or next input. A separate
   # inference-disabled verification relay cannot block legitimate background model calls.
   verifier=None
   try:
    if task=='W3':acc=E.evaluate_data(run,family,tag)
    else:
     (trace/'verification-relay').mkdir(exist_ok=True);verifier=AuditedRelay(trace/'verification-relay',family,BUDGET,inference_authorized=False,business=business);acc=E.evaluate_business(run,family,business,verifier)
    save(trace/'acceptance.json',acc);save(trace/'gateway-response.json',response);quiet(relay);snapshot=read(group);save(trace/'resources.json',snapshot);model_responses=relay.responses[before_responses:]
    rec=dict(unit=unit,family=family,task=task,episode=episode,session_key=session,same_service_namespace_pid=gateway.process.pid,passed=bool(acc.get('passed')) and response.get('status')==200 and failure is None,failure=failure,seconds=delivery_seconds,observed_phase_seconds=time.monotonic()-started,model_calls=relay.calls-before_calls,first_global_call=before_calls+1,last_global_call=relay.calls,cost_estimated_CNY=sum(x.get('estimated_cost_CNY') or 0 for x in model_responses),cost_incomplete=len(model_responses)!=relay.calls-before_calls or any(x.get('usage_completeness')!='terminal_observed' or not x.get('usage') for x in model_responses),resources_cumulative=snapshot,resources_before=before,model_responses=model_responses,cost_scope='Temporal episode attribution includes its observed auxiliary calls. Profile total is authoritative when background work crosses episode boundaries.')
    save(trace/'result.json',rec);results.append(rec);shutil.copytree(run/'workspace',trace/'workspace-artifacts',dirs_exist_ok=True);print('REUSE_DONE',unit,family,episode,rec['passed'],round(delivery_seconds),round(rec['cost_estimated_CNY'],5),flush=True)
   finally:
    if verifier:verifier.close()
   if failure=='fixed_model_policy':raise RuntimeError('Fixed model gate failed; do not grade configuration error')
   if failure:
    # Do not silently restart to manufacture same-service reuse. Remaining planned episodes
    # are preserved as unexecuted for this profile and need separately reported recovery.
    break
 finally:
  quiet(relay);gateway.stop();quiet(relay,seconds=.5,maximum=8);relay.close();save(run/'profile-resources.json',read(group))
 total=sum(x.get('estimated_cost_CNY') or 0 for x in relay.responses);valid=sum(x['passed'] for x in results[1:]);rec=dict(unit=unit,family=family,task=task,episodes=results,training_cost=results[0]['cost_estimated_CNY'] if results else None,total_cost=total,all_profile_model_calls=relay.calls,cost_incomplete=len(relay.responses)!=relay.calls or any(x.get('usage_completeness')!='terminal_observed' or not x.get('usage') for x in relay.responses),valid_new_deliveries=valid,amortized_cost_per_valid_delivery=total/valid if valid else None,profile_seconds=time.monotonic()-profile_started,scope='One continuously running native Gateway, same profile, three distinct session keys. Native asset use must be proven from actual request/read provenance; persistent program reuse is not automatically native memory learning.')
 save(run/'result.json',rec);return rec

def main():
 os.chdir(OLD);results=[]
 for unit in range(1,7):
  for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):results.append(run_profile(unit,family));save(R/'results/reuse.json',results)
 print('REUSE_COMPLETE',len(results),flush=True)
 from run_setup_imports import main as check_setup_imports
 check_setup_imports()
 from run_install_rebuild import main as check_install_rebuilds
 check_install_rebuilds()
if __name__=='__main__':main()
