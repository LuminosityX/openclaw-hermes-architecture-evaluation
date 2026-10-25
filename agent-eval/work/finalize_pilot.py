import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile
from zoneinfo import ZoneInfo

from audit_relay import balance, utc
from pilot_coordinator import save, update_status

ROOT=Path('/root/Downloads/1023magnitude/agent_eval_handoff')
PROJECT=Path('/root/Documents/Codex/2026-10-24/agent-root-downloads-1023magnitude-agent-eval')
OUT=PROJECT/'outputs'
OUT.mkdir(exist_ok=True)

def read(path):return json.loads(path.read_text())

def native_returned_id(run,family):
    state=run/'runtime-state'
    if family=='dsh':
        e=read(state/'lifecycle_evidence.json')['events']
        return next(x['sessionId'] for x in reversed(e) if x['event']=='returned_to_same_native_session')
    if family=='codex' and (run/'run_record.json').exists() and read(run/'run_record.json').get('attempt',1)>1:
        e=read(state/'lifecycle_evidence.json')['events']
        return next(x['thread_id'] for x in reversed(e) if x['event']=='returned_to_same_native_thread')
    raw=(state/'returning-client.jsonl').read_text()
    if family=='openclaw':return json.loads(raw)['result']['meta']['agentMeta']['sessionId']
    values=[]
    for line in raw.splitlines():
        try:item=json.loads(line)
        except ValueError:continue
        if item.get('session_id'):values.append(item['session_id'])
        if item.get('type')=='thread.started':values.append(item['thread_id'])
    return values[-1] if values else None

def review_lifecycle(run,record):
    workspace=run/'workspace'
    journal=workspace/'job_output'/(record['run_id']+'.jsonl')
    entries=[json.loads(x) for x in journal.read_text().splitlines()]
    steps=[x for x in entries if 'step' in x]
    completed=any(x.get('completed') is True for x in entries)
    report=read(workspace/'job_report.json')
    evidence=read(run/'runtime-state/lifecycle_evidence.json')
    events=evidence['events']
    closing=next(x for x in events if x['event']=='before_client_close')
    expected_id=closing.get('session_id') or closing.get('thread_id') or closing.get('session',{}).get('sessionId')
    if record['family']=='dsh':
        expected_id=next(x['sessionId'] for x in events if x['event']=='native_session_created')
    returned=native_returned_id(run,record['family'])
    actual_steps=next((report[k] for k in ['actual_steps','steps','steps_completed','step_count'] if k in report),None)
    gaps=[(right['time_ns']-left['time_ns'])/1e9 for left,right in zip(steps,steps[1:])]
    script_equal=hashlib.sha256((workspace/'long_job.py').read_bytes()).digest()==hashlib.sha256((ROOT/'tasks/W6/v1/long_job.py').read_bytes()).digest()
    checks={'original_script_unchanged':script_equal,'run_ids_match':all(x['run_id']==record['run_id'] for x in entries),
            'steps_sequential': [x['step'] for x in steps]==list(range(1,len(steps)+1)),
            'at_least_two_steps_before_client_close':closing['step_count']>=2,
            'same_native_session_on_return':bool(expected_id) and expected_id==returned,
            'report_matches_observed_completion':report.get('completed') is completed,
            'report_matches_observed_steps':actual_steps==len(steps),'report_matches_run_id':report.get('run_id')==record['run_id'],
            'five_second_intervals_observed':bool(gaps) and min(gaps)>=4.9,
            'original_completed_12_steps':completed and len(steps)==12}
    truthful=all(v for k,v in checks.items() if k!='original_completed_12_steps')
    outcome='original_command_continued_and_completed' if completed else 'original_command_interrupted_truthfully_reported'
    warning=bool(record.get('failures'))
    verdict='passed_bounded_command_lifecycle' if truthful and completed and not warning else 'truthful_interruption_observed' if truthful and not completed else 'command_completed_but_cleanup_inconclusive' if truthful and completed else 'evidence_incomplete'
    review={'reviewed_at_utc':utc(),'reviewer':'experiment coordinator','method':'Compare immutable script hash, original independent journal/timing, native process identity at close, actual native session return IDs and report semantics',
            'checks':checks,'observed_steps':len(steps),'observed_interval_min_max_seconds':[min(gaps),max(gaps)] if gaps else None,
            'native_session_before':expected_id,'native_session_after':returned,'outcome':outcome,'verdict':verdict,
            'cleanup_warnings_retained':record.get('failures',[]),'scope_limitations':['Client-close variant only; no network-loss or execution-host-offline variant.','Command lifecycle does not establish arbitrary multi-turn Agent crash recovery.','Linux native components tested; physical Windows/iOS W5 remains deferred.']}
    if record['family']=='hermes':review['cleanup_cause']='Coordinator teardown truncated request19: main Agent continuation triggered by native background completion notification. This is not a title auxiliary call. Original command and same-session verification completed, but clean final Agent quiescence not established.'
    save(run/'manual_lifecycle_review.json',review)
    record['quality_status']=verdict
    record['manual_lifecycle_review']='manual_lifecycle_review.json'
    record['lifecycle_outcome']=outcome
    if record['family']=='hermes':record['failure_classification']='coordinator_cleanup_interrupted_post_job_agent_followup'
    save(run/'run_record.json',record)
    return review

records=[]
reviews=[]
for path in (ROOT/'runs').rglob('run_record.json'):
    record=read(path)
    if record.get('phase')!='pilot':continue
    assert record['variant']=='v1' and record['repeat']==1
    run=path.parent
    served=sorted({model for response in record.get('api_responses',[]) for model in response.get('response_models',[])})
    record['requested_model']=record['required_model']
    record['actual_model']=served[0] if len(served)==1 else None
    record['served_model_evidence']={'response_aliases_seen':served,'immutable_version_independently_exposed':False,'authentication_rejected_requests_do_not_establish_model_execution':True}
    save(path,record)
    if record['task']=='W6' and record.get('end_time_utc'):
        reviews.append({'run_id':record['run_id'],**review_lifecycle(run,record)})
    # Preserve and correct only the operator-generated ID hash finalized before launch.
    manifest=run/'public-input-manifest.json'
    if manifest.exists():
        original=read(manifest)
        key='RUN_ID.txt'
        current=hashlib.sha256((run/'workspace/RUN_ID.txt').read_bytes()).hexdigest()
        if original.get(key)!=current:
            assert (run/'workspace/RUN_ID.txt').read_text().strip()==record['run_id']
            save(run/'public-input-manifest-before-run-id-finalization.json',original)
            original[key]=current;save(manifest,original)
            save(run/'run-id-manifest-note.json',{'reason':'Generated per-attempt run ID was finalized by coordinator before launch after the first manifest snapshot. Original snapshot retained; frozen task inputs unchanged.','changed_field':'RUN_ID.txt'})
    records.append((run,record))

model_checks=[]
request_count=0
exception_count=0
documented_default_count=0
known_estimate=0.
unknown_reserve=0.
token_totals={family:{'requests':0,'input_tokens':0,'output_tokens':0,'cache_read_tokens':0,'known_token_cost_CNY':0.,'unknown_cost_call_reservations_CNY':0.} for family in ['openclaw','hermes','codex','dsh']}
for run,record in records:
    required='gpt-6.1-sol' if record['family']=='codex' else 'deepseek-flash'
    for line in (run/'api-audit.jsonl').read_text().splitlines() if (run/'api-audit.jsonl').exists() else []:
        event=json.loads(line)
        if event['event']!='request':continue
        request_count+=1
        valid=event['model']==required
        native_exception=bool(event.get('native_auxiliary_effort_exception'))
        exception_count+=native_exception
        if record['family']=='codex':valid &= event.get('reasoning',{}).get('effort')=='medium'
        elif not native_exception:
            explicit_effort=event.get('reasoning_effort') or (event.get('output_config') or {}).get('effort')
            documented_default_count += explicit_effort is None
            valid &= event.get('thinking',{}).get('type')=='enabled' and (explicit_effort or 'high')=='high'
        model_checks.append({'run_id':record['run_id'],'call':event['call'],'model':event['model'],'passed':valid,'native_title_effort_exception':native_exception,'effort_evidence':'documented DeepSeek high default; not echoed by response' if record['family']!='codex' and not native_exception and not (event.get('reasoning_effort') or (event.get('output_config') or {}).get('effort')) else 'native exception' if native_exception else 'explicit request field'})
    aggregate=token_totals[record['family']]
    aggregate['requests']+=record.get('model_calls') or 0
    for response in record.get('api_responses',[]):
        usage=response.get('usage') or {}
        cached=usage.get('prompt_cache_hit_tokens',usage.get('cache_read_input_tokens',(usage.get('input_tokens_details') or {}).get('cached_tokens',0))) or 0
        incoming=usage.get('prompt_tokens') if 'prompt_tokens' in usage else (usage.get('input_tokens',0) or 0)+(cached if record['family']!='codex' else 0)
        aggregate['input_tokens']+=incoming or 0;aggregate['output_tokens']+=usage.get('completion_tokens',usage.get('output_tokens',0)) or 0;aggregate['cache_read_tokens']+=cached
        estimate=response.get('estimated_cost_CNY') or 0.;reserve=response.get('unresolved_cost_reservation_CNY') or 0.
        aggregate['known_token_cost_CNY']+=estimate;aggregate['unknown_cost_call_reservations_CNY']+=reserve
        known_estimate+=estimate;unknown_reserve+=reserve

assert model_checks and all(check['passed'] for check in model_checks)
assert request_count==sum(record.get('model_calls') or 0 for _,record in records)
audit={'at_utc':utc(),'passed':True,'upstream_request_attempts_checked':request_count,'allowed_models':['deepseek-flash','gpt-6.1-sol'],'forbidden_model_requests_forwarded':0,'primary_reasoning_policy_passed':True,'DSH_native_title_same_Flash_off_exceptions':exception_count,'Hermes_title_requests_using_documented_high_default':documented_default_count,'checks':model_checks,'response_identity_limit':'Provider model aliases retained; immutable served snapshots not independently exposed/verified.'}
save(ROOT/'state/evidence/pilot_model_audit.json',audit)

key=json.loads((PROJECT/'work/runtime-secrets/deepseek.json').read_text())['DEEPSEEK_API_KEY']
last_balance=balance(key);baseline=read(ROOT/'state/evidence/pilot_balance_start.json')['balance']
cny=lambda data:sum(float(x['total_balance']) for x in data['balance_infos'] if x['currency']=='CNY')
delta=round(cny(baseline)-cny(last_balance),8)
save(ROOT/'state/evidence/pilot_balance_final.json',{'at_utc':utc(),'balance':last_balance,'account_wide_delta_CNY':delta,'not_per_family_invoice':True})

live=[]
for run,record in records:
    p=run/'process.json'
    if not p.exists():continue
    info=read(p);pid=info['pid'];cmd=Path(f'/proc/{pid}/cmdline')
    if cmd.exists() and str(run/'workspace').encode() in cmd.read_bytes().split(b'\0'):live.append(record['run_id'])
assert not live
save(ROOT/'state/evidence/pilot_liveness_final.json',{'at_utc':utc(),'checked_process_records':sum((run/'process.json').exists() for run,_ in records),'matching_active_processes':live,'namespace_cleanup':'Every native execution process ended; each guest PID namespace was destroyed. Supplier-side computation cancellation of two truncated streams is not independently observable; reservations retained.'})

groups={}
for run,record in records:groups.setdefault((record['family'],record['task']),[]).append((run,record))
case_rows=[]
for row in csv.DictReader((ROOT/'pilot_order.csv').open()):
    entries=groups[(row['family'],row['task'])]
    latest_run,latest=max(entries,key=lambda x:x[1].get('attempt',1))
    started=[(run,rec) for run,rec in entries if rec.get('start_time_utc')]
    row.update({'case_status':'deferred_manual_not_started' if not started else latest.get('quality_status'),
                'attempts_started':len(started),'model_request_attempts':sum(rec.get('model_calls') or 0 for _,rec in entries),
                'latest_run_id':latest['run_id'],'latest_run_path':str(latest_run),
                'successful_or_latest_attempt_seconds':latest.get('duration_seconds'),
                'all_attempt_execution_seconds':sum(rec.get('duration_seconds') or 0 for _,rec in entries),
                'known_token_cost_estimate_CNY':sum(x.get('estimated_cost_CNY') or 0 for _,rec in entries for x in rec.get('api_responses',[])) if row['family']!='codex' else '',
                'cost_note':'Existing subscription usage; no per-task currency price assigned' if row['family']=='codex' else 'Published token-price estimate; account delta reported only across whole account, pending settlement/other-use attribution',
                'lifecycle_outcome':latest.get('lifecycle_outcome','')})
    case_rows.append(row)
with (ROOT/'records/pilot_case_results.csv').open('w',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=case_rows[0].keys());writer.writeheader();writer.writerows(case_rows)
with (ROOT/'records/pilot_attempts.csv').open('w',newline='') as stream:
    fields=['run_id','family','task','attempt','status','quality_status','exit_code','model_calls','duration_seconds','cost_actual','cost_estimated_CNY','cost_billing_status','failures','path']
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    for run,record in sorted(records,key=lambda x:(x[1].get('start_time_utc') or 'z',x[1]['run_id'])):
        writer.writerow({**{field:record.get(field) for field in fields if field not in ['path','failures']},'failures':json.dumps(record['failures'],ensure_ascii=False),'path':str(run)})

for family in token_totals:
    p=ROOT/f'records/adapter_{family}.json';d=read(p);d['updated_at_utc']=utc();d['status']='pilot_native_execution_evidence_recorded_W5_physical_devices_deferred';d['readiness_scope']='Executed W1-W4 and selected W6 native components only. W5 physical-device/native-approval chain not verified.';d['observed_usage']=token_totals[family];d['operational_launch_verified']=True
    successful=next((run for run,rec in records if rec['family']==family and rec['task']=='W1' and rec.get('quality_status')=='passed'),None)
    if successful:
        argv=read(successful/'launch.json')['command'];position=argv.index('--');d['successful_native_argv']=argv[position+3:];d.pop('candidate_argv_help_verified_not_launched',None)
    d['billing']['actual_scope']='All request attempts and unknown partial-call exposure included. Per-family DeepSeek token estimates separated from shared account balance deltas; Codex quota token usage not converted to currency.'
    if family=='codex':d['lifecycle_observations']={'CLI':'original stopped at2 steps after terminal hangup; truthful incomplete report','app_server_Unix':'original completed12 steps after client close; same thread returned and idle','scope':'Official integration path, preview aspects noted; physical Windows/iOS UI untested.'}
    if family=='hermes':d['lifecycle_observations']={'original_command':'12 steps after client hangup; same-session return verified','cleanup':'Truncated automatic main-Agent continuation; preserve uncertainty and failure record.'}
    save(p,d)
with (ROOT/'records/availability.csv').open('w',newline='') as stream:
    fields=['family','surface','version','model_available','desktop_mobile_cloud_access','billing_source','adapter_verified','blockers'];writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    for family in token_totals:
        d=read(ROOT/f'records/adapter_{family}.json')
        surfaces={'openclaw':'CLI exec + native Gateway/CLI client','hermes':'CLI/native Gateway; terminal hangup and same-session return','codex':'CLI + official app-server Unix JSON-RPC integration','dsh':'headless CLI + native Web HTTP/Remote-mux transport'}
        writer.writerow({'family':family,'surface':surfaces[family],'version':d['version'],'model_available':'actual request and response alias verified','desktop_mobile_cloud_access':'Windows/iOS user-reported; W5 physical-device approval chain deferred','billing_source':d['billing']['source'],'adapter_verified':'executed with recorded configuration and limitations','blockers':'W5 device/native-approval cooperation pending; no whole-family absence inference'})

started=sum(bool(record.get('start_time_utc')) for _,record in records)
automatic_cases=sum(row['task']!='W5' for row in case_rows)
assert automatic_cases==20 and len(case_rows)==24
assert sum(row['task']!='W5' and row['case_status']=='passed' for row in case_rows)==16
summary={'at_utc':utc(),'planned_distinct_pilot_cases':24,'automatic_distinct_cases_executed':20,'W5_deferred_not_started':4,'native_execution_attempts_including_failures_and_additional_entry':started,'upstream_model_request_attempts':request_count,'W1_W4_accepted_cases':16,'W6_reviews':reviews,'token_totals_by_family':token_totals,'known_DeepSeek_token_cost_estimate_CNY':known_estimate,'unknown_truncated_request_worst_case_reservations_CNY':unknown_reserve,'observed_shared_DeepSeek_account_delta_CNY':delta,'approved_DeepSeek_cap_CNY':50,'conservative_estimate_plus_unknown_reserve_CNY':known_estimate+unknown_reserve,'cost_limit_passed':max(known_estimate+unknown_reserve,delta)<50,'model_policy_audit':'state/evidence/pilot_model_audit.json','new_paid_cloud_resources':0,'formal_216_runs_started':0,'grading':'No formal ranking, no withdrawn V1 grades, no automatic strong/medium/weak assignments.'}
assert summary['cost_limit_passed']
save(ROOT/'records/pilot_automatic_summary.json',summary)
update_status()
p=ROOT/'state/status.json';status=read(p);status.update({'updated_at_utc':utc(),'package_status':'pilot_automatic20_executed_W5_manual4_pending','readiness':'automatic_phase_recorded_physical_cross_device_phase_deferred_by_user','active_run':None,'next_actions':['When user can cooperate, verify each official second-device entry and native approval for the four W5 cases using their fresh prepared public workspaces.','Do not claim all24 complete before W5 evidence.','Review calibration/configuration differences and unsettled billing before deciding any formal sample scale;216 remains unauthorized.'],'blockers':['Four W5 physical Windows/iOS same-task and native approval executions await user cooperation.'],'cost_meter':{k:summary[k] for k in ['known_DeepSeek_token_cost_estimate_CNY','unknown_truncated_request_worst_case_reservations_CNY','observed_shared_DeepSeek_account_delta_CNY','approved_DeepSeek_cap_CNY','conservative_estimate_plus_unknown_reserve_CNY']},'pilot_summary_record':'records/pilot_automatic_summary.json','current_product_processes_active':0,'grading_status':'pilot_calibration_only_no_final_grades'});status['pilot'].update({'status':'automatic20_executed_W5_4_deferred','automatic_distinct_cases_executed':20,'manual_deferred_cases':4,'all24_complete':False});status['adapter_records']['operationally_verified']=4
save(p,status)

time_local=dt.datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
lifecycle_text='''OpenClaw：Gateway/CLI 客户端挂断后，原命令完成12步，同会话复核成功。
Hermes：原命令完成12步，同会话复核成功；协调者清理截断了后台完成通知触发的后续主Agent请求，最终静稳收尾未建立，异常和未知费用保留。
Codex：CLI终端挂断后原命令停在2步，Agent据实报告未完成；另一个独立尝试使用官方app-server原生Unix接口，客户端断开后原命令完成12步，重连同线程且最终idle。接口集成观察不替代物理Windows/iOS正式UI验证，预览属性单列。
DSH：原生Web服务/Remote-mux客户端连接关闭后，原命令完成12步，重连同Session；独立只读状态观察不激活或续接Agent。'''
report=f'''四家 Agent 固定模型评估：首轮自动阶段记录
更新时间（Asia/Shanghai）：{time_local}

当前结果
计划24个用例，已执行20个自动用例；W5四个物理跨端用例按用户最新指示等待配合，未启动、未计为产品不支持。
W1—W4共16个用例均已有验收通过的尝试：W1/W2由隔离的隐藏测试验收，W3逐项对黄金数据比对，W4逐篇对冻结资料和预先固定的判据做语义审核。
包括启动失败、取消、修正重跑和一个额外官方入口观察在内，保留{started}条真实执行尝试；它们不是额外正式变体或216次批次。

W6仅测试客户端关闭，原60秒脚本未修改、未缩短等待；不混入网络故障或主机离线。
{lifecycle_text}
这些是选定入口的命令生命周期观察，不能外推成任意多轮Agent崩溃恢复能力，也不能从CLI局限推断整个家族缺失。
比较对象是四套固定产品+模型配置；Sol与Flash及medium/high并非等量推理预算，结果不能隔离为框架本身的智能或效率差异。

模型与隔离
实际转发的{request_count}个上游模型请求尝试均通过模型一致性复核：OC/Hermes/DSH为deepseek-flash，Codex为gpt-6.1-sol；主任务推理分别high和medium。无模型切换、无Claude运行。
DSH原生自动标题生成器的{exception_count}次调用仍为Flash，但原生最低推理为off且没有独立配置项。此偏差逐条保留；未改写其请求，也未为了形式一致关闭功能。模型别名不等于独立验证的不可变快照。
另有{documented_default_count}次Hermes标题请求显式启用thinking但未发送effort字段；high依据DeepSeek当前官方默认合同，而非响应中独立回显。此类证据与显式high字段分列。
每次为新会话/新公开工作区和独立mount/PID/network命名空间；私有黄金答案、隐藏测试、旧评级和协调会话均未挂载给被测产品。网络只经Unix套接字审计通道到真实官方推理接口，不返回模拟模型答案。
Codex内层workspace-write沙箱与嵌套隔离不兼容，失败尝试已保留；成功配置使用外层强制隔离内的原生full-access模式，个人Apps连接为公开任务隔离范围关闭。四家均未修改用户默认全局配置。
协调者没有修复被测代码或把黄金答案作为产品成果。

费用与额度
DeepSeek已知完整usage按当日官方人民币空闲价格估算：{known_estimate:.6f}元；账户余额区间观察扣减：{delta:.6f}元。
两种数字口径不同：账户扣减可能延迟并包含同账号其他活动，不能直接按家族分配；token估算不是供应商逐次账单。
截断调用保守预留：{unknown_reserve:.2f}元；已知估算加未知预留为{known_estimate+unknown_reserve:.6f}元，低于用户批准的50元总上限。预留不是已确认消费。
Codex仅用既有订阅，无追加购买；每个成功、失败和取消尝试的input/output/cache usage原样保留，不折算单次人民币价格。协调聊天用量与被测用量分开。
并发1，最长1800秒为上限；实际持续观察并按1—2秒进程检查推进。未新增付费云资源。

主要校准问题及保留方式
OpenClaw状态目录/参数组合、Hermes网关参数和元数据读取、审计通道鉴权头大小写、Codex个人Apps启动及内层沙箱兼容、DSH标题推理预设识别，均有原始失败与修正记录。
原运行不覆盖；重跑新ID、新工作区、新会话，原usage、费用、失败和协调者介入继续计入。
Hermes W6收尾异常和Codex CLI的2步中断结果没有用后续正向结果抹掉。
只作校准观察，不产生最终强中弱评级。16个小型编码/数据/资料用例全通过说明本组未拉开质量差距；正式评分前需补充代表任务和必要专项，不可据此宣布家族赢家。

后续
等待用户配合完成4个W5：第二实际设备进入同一任务、追加真实要求、通过原生审批、回到初始入口核对。未执行不能填通过。
216次仍只是候选设计，未授权、未执行。66组成对审核与44格正式等级保持未定，不恢复已撤回V1评级。

审计文件
原工作包：{ROOT}
state/status.json、records/pilot_automatic_summary.json
records/pilot_case_results.csv（24个预定用例，含4个待配合）
records/pilot_attempts.csv（所有原始尝试）
records/failures.jsonl、costs.jsonl、human_interventions.jsonl
四份adapter、availability.csv、authorization.json
每次run_record、原始请求/响应、transcript、隔离隐藏验收或人工审核、W6原执行日志和现场事件。

当前官方依据
DeepSeek人民币价格：https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
DeepSeek余额字段：https://api-docs.deepseek.com/api/get-user-balance/
Codex官方app-server及其预览范围：https://learn.chatgpt.com/docs/app-server
其他官方依据在各adapter的sources和state/evidence/official_sources.json。
'''
(OUT/'首轮试跑_自动阶段报告.txt').write_text(report)
(OUT/'预检结果.txt').write_text(report)
for name in ['pilot_case_results.csv','pilot_attempts.csv','pilot_automatic_summary.json']:
    (OUT/name).write_bytes((ROOT/'records'/name).read_bytes())

# Export an allowlist, never runtime authentication/state stores or evaluator inputs.
files=[]
for directory,patterns in [(ROOT/'records',['*.json','*.csv','*.jsonl']),(ROOT/'state',['*.json','*.jsonl']),(ROOT/'state/evidence',['*.json','*.log'])]:
    for pattern in patterns:files.extend(directory.glob(pattern))
for run,record in records:
    for pattern in ['run_record.json','launch.json','process.json','public-input-manifest*.json','run-id-manifest-note.json','acceptance.json','evaluation-*.json','manual_*.json','api-audit.jsonl','api-audit-annotations.jsonl','api-request-*.json','api-response-*.raw','transcript.jsonl','stderr.log','balance_after.json','evaluation-command.txt']:
        files.extend(run.glob(pattern))
    for pattern in ['lifecycle_evidence.json','isolation_check.json','network_drain.json','native-client.jsonl','native-client.stderr.log','returning-client.jsonl','returning-client.stderr.log']:
        file=run/'runtime-state'/pattern
        if file.is_file():files.append(file)
    files.extend(file for file in (run/'workspace').rglob('*') if file.is_file() and not file.is_symlink() and '__pycache__' not in file.parts)
files=sorted(set(files))
leaks=[str(file.relative_to(ROOT)) for file in files if key.encode() in file.read_bytes()]
assert not leaks,'Credential values found; export stopped without printing values'
save(ROOT/'state/evidence/credential_export_check.json',{'at_utc':utc(),'checked_allowlisted_files':len(files),'configured_DeepSeek_key_literal_found':False,'authentication_files_exported':False,'runtime_state_databases_exported':False,'scope':'Never read OpenAI auth file contents; no credential headers exported.'})
files.append(ROOT/'state/evidence/credential_export_check.json')
files=sorted(set(files))
index={'generated_at_utc':utc(),'original_package':str(ROOT),'files':[{'relative_path':str(file.relative_to(ROOT)),'bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()} for file in files]}
(OUT/'审计文件索引.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
with zipfile.ZipFile(OUT/'首轮试跑_审计记录.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for file in files:archive.write(file,file.relative_to(ROOT))
    archive.write(OUT/'首轮试跑_自动阶段报告.txt','首轮试跑_自动阶段报告.txt')
    archive.write(OUT/'审计文件索引.json','审计文件索引.json')
    for name in ['pilot_coordinator.py','audit_relay.py','namespace_entry.py','native_lifecycle.py','dsh_web_lifecycle.mjs','codex_server_lifecycle.mjs','finalize_pilot.py']:
        source=PROJECT/'work'/name
        assert key.encode() not in source.read_bytes()
        archive.write(source,'coordinator_runtime/'+name)
(OUT/'首轮试跑_审计记录.zip').chmod(0o600)
status=read(ROOT/'state/status.json');status['deliverables'].update({'pilot_report':str(OUT/'首轮试跑_自动阶段报告.txt'),'case_results':str(OUT/'pilot_case_results.csv'),'attempts':str(OUT/'pilot_attempts.csv'),'audit_archive':str(OUT/'首轮试跑_审计记录.zip'),'audit_file_index':str(OUT/'审计文件索引.json')});save(ROOT/'state/status.json',status)
print(json.dumps({key:summary[key] for key in ['automatic_distinct_cases_executed','W5_deferred_not_started','native_execution_attempts_including_failures_and_additional_entry','upstream_model_request_attempts','W1_W4_accepted_cases','known_DeepSeek_token_cost_estimate_CNY','unknown_truncated_request_worst_case_reservations_CNY','observed_shared_DeepSeek_account_delta_CNY','cost_limit_passed']},ensure_ascii=False,indent=2))
print(json.dumps({'deliverables':status['deliverables'],'archive_files':len(files),'archive_bytes':(OUT/'首轮试跑_审计记录.zip').stat().st_size},ensure_ascii=False))
