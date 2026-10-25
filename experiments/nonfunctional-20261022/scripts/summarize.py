import csv,html,json,sqlite3,statistics
from pathlib import Path
R=Path(__file__).resolve().parents[1];F=['openclaw','hermes']
load=lambda name:json.loads((R/name).read_text())
http=load('results/http-runs.json');tools=load('results/tool-matched-runs.json');audit=[json.loads(x)for x in(R/'raw/provider-audit.jsonl').read_text().splitlines()]
metrics=[];checks={};excluded=[]
def med(values):return statistics.median(values)
def add(id,dimension,mechanism,design,label,unit,values,n,direction='lower',note='',source=None):
    assert set(values)==set(F)
    metrics.append(dict(id=id,dimension=dimension,mechanism=mechanism,design=design,label=label,unit=unit,values=values,n=n,direction=direction,note=note,source=source or [],different=values[F[0]]!=values[F[1]]))
text={f:[x for x in http if x['framework']==f and '-text-'in x['run_id']]for f in F}
tool={f:[x for x in tools if x['framework']==f]for f in F}
checks['real_model_acceptance']=all(x['correct']for x in http+tools)
for code in[429,503]:
    values={};detail={}
    for f in F:
        run=f+'-fault-'+str(code);case=next(x for x in http if x['run_id']==run);fail=[x for x in audit if x['run_id']==run and x.get('injected')];success=[x for x in audit if not x.get('injected')and x['framework']==f and case['token']in json.dumps(x.get('request_messages',[]),ensure_ascii=False)]
        assert len(fail)==1 and fail[0]['status']==code and case['correct']and success
        first=min(success,key=lambda x:x['request_start']);values[f]=(first['request_start']-fail[0]['end'])*1000;detail[f]={'injected_status':code,'retry_started':first['request_start'],'error_sent':fail[0]['end'],'final_correct':case['correct']}
    add('retry-'+str(code),'1. 可靠性与可恢复性','模型请求暂时失败后的自动重试',f'在模型入口实际返回一次HTTP {code}错误，随后恢复转发至真实DeepSeek；各测试1次。',f'HTTP {code}后再次发起请求前的等待','ms',values,{f:1 for f in F},note='受控故障注入，不是DeepSeek实际发生故障；未测进程崩溃恢复。',source=[detail])
timeout={f:load('raw/timeout-'+f+'.json')for f in F}
checks['timeout_actual_processes']=all(x['started']and x['surviving_processes']==0 and not x['heartbeat_continued']for f in F for x in timeout[f])
add('command-timeout','3. 可控性','命令超时后停止执行并清理子进程','实际启动持续写入标记的父子进程，设置1秒超时；检查命令返回及进程清理，各5次。','1秒超时命令的实际返回等待','ms',{f:med([x['wall_ms']for x in timeout[f]])for f in F},{f:5 for f in F},note='两边所有父子进程均已停止；本项是命令时限，不代表会话/stop体验。')
for key,label in[('first_text_ms','短回复：看到第一段文字的等待'),('total_ms','短回复：收到完整结果的等待')]:
    add('text-'+key,'4. 性能与响应性','HTTP入口的流式回复', '服务启动并预热后，交替发送相同类型的短回复请求，使用真实DeepSeek；各3次。',label,'ms',{f:med([x[key]for x in text[f]])for f in F},{f:3 for f in F},note='从HTTP客户端发出请求计时，包含模型及网络等待；首次文字只计实际文本，不计心跳。')
add('tool-complete','4. 性能与响应性','模型调用工具并交付文件结果','两边均允许测试命令自动执行；让DeepSeek读取5个数、求和并写出JSON，独立检查产物，各3次。','文件任务完成等待','ms',{f:med([x['total_ms']for x in tool[f]])for f in F},{f:3 for f in F},note='采用权限已对齐的重测；早期权限不一致的数据不用于比较。')
usage_details={}
for kind,groups in [('text',text),('tool',tool)]:
    details={}
    for f in F:
        details[f]=[]
        for x in groups[f]:
            calls=[v for v in audit if v['framework']==f and v.get('status')==200 and not v.get('injected')and x['token']in json.dumps(v.get('request_messages',[]),ensure_ascii=False)]
            assert calls and all(v.get('usage',{}).get('prompt_tokens',0)>0 for v in calls)
            details[f].append({'token':x['token'],'prompt_tokens':sum(v['usage']['prompt_tokens']for v in calls),'completion_tokens':sum(v['usage'].get('completion_tokens',0)for v in calls),'api_calls':len(calls)})
    usage_details[kind]=details
    title='短回复'if kind=='text'else'文件任务'
    for key,unit,label in [('prompt_tokens','Token',title+'：每次成功任务消耗的输入Token'),('api_calls','次',title+'：每次成功任务的模型请求数')]:
        add('usage-'+kind+'-'+key,'5. 资源与成本效率','系统提示、工具说明和辅助模型请求的额外消耗',f'沿用同一组{title}测试，按任务逐次汇总DeepSeek实际返回的用量；各3次。',label,unit,{f:med([x[key]for x in details[f]])for f in F},{f:3 for f in F},note='计入匹配到该任务的标题生成等辅助请求；Token不是账单金额，缓存Token不等于同价计费。',source=[details])
for key,label,unit,direction in [('makespan_ms','4个请求全部完成的等待','ms','lower'),('throughput_per_second','同时处理4个请求时的完成速度','请求/秒','higher')]:
    groups={f:[load(f'raw/batch-{f}-concurrency4-{i}.json')for i in range(2)]for f in F};assert all(x['completed']==4 for f in F for x in groups[f])
    add('concurrency-'+key,'6. 可伸缩性','独立会话请求的并发处理','同时从4个独立会话发送短回复请求，检查4个结果均正确；每边测2批，共8请求。',label,unit,{f:med([x[key]for x in groups[f]])for f in F},{f:2 for f in F},direction,note='只代表本机4并发短回复，不推断更大规模吞吐或公平性。')
observations={}
for f in F:
    out=[]
    if f=='openclaw':
        p=R/'runtime/openclaw/agents/main/agent/openclaw-agent.sqlite';c=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True)
        for case in tool[f]:
            sessions=c.execute('select distinct session_id from transcript_events where event_json like ?',('%'+case['token']+'%',)).fetchall();assert len(sessions)==1
            for(raw,)in c.execute('select event_json from transcript_events where session_id=?',sessions[0]):
                if not raw:continue
                v=json.loads(raw);m=v.get('message',{})
                if m.get('role')!='toolResult':continue
                d=m.get('details',{})
                if d.get('status')in['blocked','denied']:continue
                out.append({'token':case['token'],'call_id':m.get('toolCallId'),'tool':m.get('toolName'),'duration_recorded':isinstance(d.get('durationMs'),(int,float)),'duration_ms':d.get('durationMs'),'exit_code':d.get('exitCode')})
    else:
        p=R/'runtime/hermes/state.db';c=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True)
        for case in tool[f]:
            sessions=c.execute('select distinct session_id from messages where content like ?',('%'+case['token']+'%',)).fetchall();assert len(sessions)==1
            for call,name,raw in c.execute("select tool_call_id,tool_name,content from messages where session_id=? and role='tool'",sessions[0]):
                try:d=json.loads(raw)
                except ValueError:continue
                if d.get('status')in['blocked','denied']:continue
                duration=next((d[k]for k in['duration_ms','durationMs','duration','elapsed_ms']if isinstance(d.get(k),(int,float))),None)
                out.append({'token':case['token'],'call_id':call,'tool':name,'duration_recorded':duration is not None,'duration_ms':duration,'exit_code':d.get('exit_code')})
    assert out;observations[f]=out
add('tool-duration-record','9. 可观测性与可审计性','默认会话记录中的工具耗时保存','沿用3个真实文件任务，逐条读取原生会话数据库，检查实际执行的每次工具调用是否留有耗时字段。','可直接查到耗时的工具调用比例','%',{f:sum(x['duration_recorded']for x in observations[f])/len(observations[f])*100 for f in F},{f:len(observations[f])for f in F},'higher',note='只检查当前默认会话记录；未启用额外观测Hook，不代表框架无法导出耗时。',source=[observations])
backups={f:[x for x in load('raw/backup-files-'+f+'.json')if not x['warmup']]for f in F};checks['backup_file_integrity']=all(x['correct_files']==64 for f in F for x in backups[f])
for key,label in[('backup_ms','相同文件数据的备份等待'),('restore_ms','相同文件数据的恢复等待')]:
    add('files-'+key,'10. 可维护性与可运维性','原生备份归档与文件恢复','两边使用相同64个文件、共2 MiB，调用原生备份及恢复到新目录，并逐文件校验内容；各3次。',label,'ms',{f:med([x[key]for x in backups[f]])for f in F},{f:3 for f in F},note='只测文件数据与最小配置，不含会话数据库、升级迁移或恢复后服务启动；归档格式沿用各自原生实现。')
mcp={f:[x for x in load('raw/mcp-'+f+'.json')if not x['warmup']]for f in F};checks['real_mcp_roundtrip']=all(x['valid']for f in F for x in mcp[f]);checks['canaries_filtered']=all(not any(x['canaries'].values())for f in F for x in mcp[f])
add('mcp-ready','11. 兼容性','启动外部MCP服务并完成协议接入','实际启动同一个MCP服务，完成握手、工具发现和首次调用；预热后各建立5次新连接。','外部工具首次可用等待','ms',{f:med([x['ready_ms']for x in mcp[f]])for f in F},{f:5 for f in F},note='相同真实stdio MCP子进程与协议流程，服务负载为本地测试工具；不外推HTTP/SSE连接。')
add('mcp-secrets','2. 安全性与隔离性','MCP子进程继承环境变量时的凭证过滤','在框架父进程设置7种合成测试凭证，实际启动MCP工具进程并读取这些凭证是否可见；各5次。','工具进程可见的测试凭证数','个',{f:med([sum(x['canaries'].values())for x in mcp[f]])for f in F},{f:5 for f in F},note='两边均为0，暂不进入差异表；仅测试合成凭证，未向工具提供真实密钥。')
assert all(checks.values()),checks
shown=[m for m in metrics if m['different']];equal=[m for m in metrics if not m['different']]
result={'checks':checks,'dimensions_tested':[1,2,3,4,5,6,9,10,11],'not_tested':{'7':'本轮未安装新插件并验证升级/卸载，不用静态代码行数代替扩展体验。','8':'未迁移到另一台机器或不同操作系统，不用同机路径复制代替跨环境迁移。'},'metrics':metrics,'shown':len(shown),'equal_excluded':[m['id']for m in equal],'usage_details':usage_details,'observability':observations}
(R/'results/summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
with(R/'results/chart-data.csv').open('w',newline='')as f:
    w=csv.writer(f);w.writerow(['ID','评估维度','考察机制点','实验设计','体验指标','单位','OpenClaw','Hermes','OpenClaw样本数','Hermes样本数','方向','采用说明'])
    for m in shown:w.writerow([m['id'],m['dimension'],m['mechanism'],m['design'],m['label'],m['unit'],m['values']['openclaw'],m['values']['hermes'],m['n']['openclaw'],m['n']['hermes'],m['direction'],m['note']])
def value(m,f):
    v=m['values'][f];s=f'{v:.1f}'if m['unit']=='ms'else(f'{v:.2f}'if m['unit']=='请求/秒'else f'{v:g}')
    if m['unit']=='%':return f'**{s}%**（{round(v*m["n"][f]/100)}/{m["n"][f]}）'
    return f'**{s} {m["unit"]}**'
headers=['评估维度','考察机制点','实验设计','体验指标','OpenClaw','Hermes Agent']
table='<table header-row="true">\n<colgroup>\n'+''.join(f'<col width="{n}"/>\n'for n in[170,250,380,270,150,150])+'</colgroup>\n<tr color="gray_bg">'+''.join(f'<td>**{h}**</td>'for h in headers)+'</tr>\n'
for m in shown:
    sample='各'+str(m['n']['openclaw'])+'次'if m['n']['openclaw']==m['n']['hermes']else f'OpenClaw {m["n"]["openclaw"]}次，Hermes {m["n"]["hermes"]}次'
    label=m['label']+f'（{m["unit"]}）'+('<br>越低越好'if m['direction']=='lower'else'<br>越高越好')
    if m['id']=='tool-duration-record':label+='<br>'+sample
    cells=[m['dimension'],m['mechanism'],m['design'],label,value(m,'openclaw'),value(m,'hermes')];table+='<tr>'+''.join(f'<td>{s}</td>'for s in cells)+'</tr>\n'
table+='</table>'
body='对应<mention url="https://app.notion.com/p/4002817dde3b8075a156d265928bb178">非功能维度对比</mention>的实测结果。已测9个维度；下表只保留本轮数值不同的指标。先说明考察机制，再列实验设计与体验指标。数值为本轮固定配置下的小样本结果。\n\n'+table+'\n\n**实验环境**：同一台Ubuntu 24.04机器，4核CPU、约7.4 GiB内存。OpenClaw和Hermes各运行一个真实HTTP服务，统一接入deepseek-flash，关闭深度思考。模型由真实DeepSeek服务完成；429/503故障由本地转发入口注入，随后恢复真实模型调用。命令与MCP工具进程均实际执行。\n\n**读表说明**：ms为毫秒；除故障各1次及明确列出的比例外，显示各组中位数。网络、模型服务波动以及两边各自的默认提示和辅助请求都可能影响本轮等待。Token来自服务商响应，不折算未经核实的账单金额；计入该任务自动产生的辅助模型请求。\n\n**范围**：未测真实IM、进程崩溃后的自动续跑、跨机器迁移和插件升级；不以组件判断替代这些场景。安全测试中，两边MCP工具进程均看不到7种测试凭证，结果相同，暂不放进差异表。\n\n<toggle>\n复核范围与原始记录\n\n'+''.join(m['label']+'：'+m['note']+'<br>'for m in shown)+'固定版本：OpenClaw [1b58cb9](https://github.com/openclaw/openclaw/tree/1b58cb9a1b4f4353e1add63c8506db4d890962e8)，Hermes [5b147ab](https://github.com/NousResearch/hermes-agent/tree/5b147ab036d6d19131bff8d20701b5001eab844a)。Node.js 24.16.0、Python 3.12.3。早期接入参数检查、权限未对齐的文件任务、两份不同历史状态的备份测试均单独保存，不用于本表比较。\n</toggle>'
(R/'results/notion-draft.md').write_text(body)
print(json.dumps({'checks':checks,'shown':len(shown),'equal_excluded':[m['id']for m in equal],'metrics':[{k:m[k]for k in['id','dimension','label','values','n']}for m in shown]},ensure_ascii=False))
