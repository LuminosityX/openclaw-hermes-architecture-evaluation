import json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
defs={
1:('消息路由','会话键隔离与连续性契约通过率','原生会话键构造器；DM、群、平台、账号/配置命名空间与thread隔离/连续性。','两边原生支持的会话作用域不同，部分用例使用各自配置语义。未接入真实IM收发或路由目标Agent。',{'openclaw':['src/routing/session-key.ts:buildAgentPeerSessionKey','src/routing/session-key.ts:resolveThreadSessionKeys'],'hermes':['gateway/session.py:build_session_key']}),
3:('接入安全','DM发送者白名单准入通过率','12组相同合成发送者与白名单；原生准入决策，覆盖允许、拒绝、空名单、通配、重复、大小写与部分ID。','Hermes使用真实授权mixin，隔离适配器/配对存储等非测试入口；未测HTTP令牌、签名、过期凭证。',{'openclaw':['src/channels/message-access/state.ts:resolveChannelIngressState','src/channels/message-access/decision.ts:decideChannelIngress'],'hermes':['gateway/authz_mixin.py:GatewayAuthorizationMixin._is_user_authorized']}),
4:('工作空间管理','任务工作目录相对路径归属通过率','两个独立工作空间中，同名、子目录、空格、中文、规范化路径，验证原生工具路径解析归属。','只测目录选择与路径解析，未运行并发文件修改、生命周期、引导文件或容器隔离。',{'openclaw':['src/agents/agent-scope-config.ts:resolveAgentWorkspaceDir','src/agents/sandbox-paths.ts:resolveSandboxInputPath'],'hermes':['tools/terminal_tool.py:record_session_cwd','tools/file_tools_paths.py:_resolve_path_for_task']}),
17:('模型请求管理','Retry-After正等待时间决策通过率','原生模型错误冷却时间读取；同12种response.headers，覆盖标准整数等待值、大小写、空值与不可解析值。0/缺失/无效均归一为无正等待时间。','只测模型错误元数据处理，未测网络重试、实际等待、凭证轮换或模型回退。Hermes对1.5秒的小数兼容与OpenClaw严格整数语义不同，另存retry-compat原始记录，不计入主指标或质量排名。',{'openclaw':['packages/ai/src/internal/retry-after.ts:parseRetryAfterErrorSeconds'],'hermes':['agent/retry_utils.py:provider_retry_after_seconds']}),
19:('智能体安全','显式禁止执行策略优先级通过率','原生命令策略组件；OpenClaw security=deny在12种授权/分析变体下拒绝；Hermes approvals.deny=[*]在mode=off与12种命令形式下拒绝。命令只评估不执行。','两个框架的策略输入不同，此图只表明各自显式禁止配置生效。未测提示注入、秘密泄漏、越权文件、审批端到端或子Agent权限。',{'openclaw':['src/node-host/exec-policy.ts:evaluateSystemRunPolicy'],'hermes':['tools/approval.py:check_dangerous_command']}),
10:('任务管理','持久化定时任务生命周期通过率','相同的定时任务创建、查询、暂停、恢复、修改、删除与重载契约；调用各自原生调度存储API。','不包含实际模型任务执行、优先级、依赖图、崩溃恢复或分布式领取。',{'openclaw':['src/cron/service.ts:CronService'],'hermes':['cron/jobs.py:create_job','cron/jobs.py:update_job','cron/jobs.py:pause_job','cron/jobs.py:resume_job','cron/jobs.py:remove_job']}),
}
raw={fw:json.loads((R/f'raw/extended-controls/{fw}.json').read_text()) for fw in ['openclaw','hermes']}
for row,(title,metric,scope,limit,entry) in defs.items():
 if not all(str(row) in raw[fw] for fw in raw):continue
 fws={}
 for fw in raw:
  cases=raw[fw][str(row)];values=[int(c['passed']) for c in cases]
  fws[fw]=dict(values=values,passed=sum(values),total=len(values),entrypoints=entry[fw],evidence=[f'raw/extended-controls/{fw}.json'])
 obj=dict(row=row,title=title,metric=metric,unit='%',direction='higher',scope=scope,limitations=[limit,'小规模固定契约用例集，无统计外推；同为100%时无法据此排名。'],status='measured',frameworks=fws)
 (R/f'results/extended-row-{row:02}.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2))
 print(row,{fw:f'{fws[fw]["passed"]}/{fws[fw]["total"]}' for fw in fws})
