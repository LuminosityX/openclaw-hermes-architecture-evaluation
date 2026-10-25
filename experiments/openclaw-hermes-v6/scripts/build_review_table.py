"""Reviewable 11-row progress/result matrix. No invented grades for missing evidence."""
import csv,html,json,time
from pathlib import Path
from runtime import R,save
D=Path('/root/output/oc-hermes-formal-design-20261024')
TEXT={
'D01':('所有者重启及待投递子任务能自动接续，但本轮工具插件退出会中断整个网关。','工具插件宿主退出未带倒网关，但所有者重启需核对未知执行，子结果需显式续接。'),
'D02':('已配置的原生容器边界和故障拒绝均通过，受信任宿主插件与MCP仍需单独管理。','同等容器边界和凭据过滤也通过；插件进程外置本身不构成恶意代码的权限沙箱。'),
'D03':('有效拒绝、撤权和取消均生效，且必需策略片段损坏时停止执行，强于对手的警告后回退。','常规拒绝、撤权和取消均生效，但受管策略层损坏后警告并忽略该层，严格策略故障防护较弱。'),
'D04':('真实任务整体耗时相当；同连接8个只读MCP工具约0.20秒，优于对手约1.61秒，但网关首字更慢。','网关首字领先；同连接MCP调用串行，8工具约1.61秒，尚未形成真实任务整体耗时领先。'),
'D05':('等待完整复用账本；首次任务的完整进程树内存与CPU均高于对手，API费用差距尚不确定。','等待完整复用账本；首次任务的内存与CPU更低，但尚不能等同于所有场景API费用更低。'),
'D06':('同等16并发上限的受控网关测试中扩展效率落后，503退避更好未抵消该差距。','同等条件下扩展效率约为对手1.53倍；这支持单网关领先，不代表自带跨节点自动接管。'),
'D07':('工具、钩子、上下文和执行器均可用公开接口扩展，并通过更新、禁用和卸载，未出现必须改核心的差距。','同样完成四类公开扩展及生命周期；Provider/ACP接入路径与对手不同，但未产生验收上的劣势。'),
'D08':('更换逻辑状态路径后文件和会话保留，但旧停用计划任务未出现在新路径的活动分区；跨OS未测。','更换逻辑HOME后文件和历史保留，但旧会话执行凭据因profile绑定而拒绝续接；跨OS未测。'),
'D09':('等待官方观测方案的原生事件、审批关联及采集端故障验收。','等待官方Relay观测方案验收；不能因默认日志缺少审批UUID就断言没有可配置审计。'),
'D10':('固定版本升级、备份回滚和损坏恢复通过，安装重建及可比操作负担仍待完整验收。','对应固定版本升级、备份回滚和损坏恢复也通过，不能把实验配置修复算作产品运维成本。'),
'D11':('三种模型线协议及两种MCP传输已实际调用；外部格式与迁入行为仍待收尾。','同样通过协议调用，结构化MCP数据并未丢失；格式与官方迁入插件仍待收尾。')}

def load(name,default):
 p=R/'results'/(name+'.json');return json.loads(p.read_text()) if p.exists() else default

def main():
 protocol=json.loads((D/'protocol_v1.json').read_text());scores=load('final-grades',load('partial-grades',{}));obs=load('observations',{});by={x['id']:x for x in scores.get('dimensions',[])};rows=[]
 for d in protocol['dimensions']:
  score=by.get(d['id'],{});g=score.get('grades',{});why=TEXT[d['id']];reviewed=load('reviewed-dimension-explanations',{}).get(d['id']);
  if reviewed:
   if reviewed.get('grades')!=g:raise RuntimeError('Reviewed explanation does not match current evidence-based grade '+d['id'])
   why=(reviewed['openclaw_reason'],reviewed['hermes_reason'])
  evidence=sorted({s for c in d['criteria'] for s in obs.get('metrics',{}).get(c['id'],{}).get('evidence',[])})
  rows.append(dict(id=d['id'],dimension=d['name'],openclaw_grade=g.get('openclaw'),openclaw_reason=why[0],hermes_grade=g.get('hermes'),hermes_reason=why[1],scorer_status=score.get('status','not_final'),coverage=score.get('distinguishable_weight',0),interval=score.get('advantage_interval',[-100,100]),evidence=evidence,criteria=d['criteria']))
 attacks=load('attacks',[]);reuse=load('reuse',[]);status=dict(at=time.time(),formal_completed=len(load('formal-task-results',[])),attacks_completed=len(attacks),reuse_profiles_completed=len(reuse),reuse_episodes_completed=len(list((R/'runs-reuse').glob('u*/*/episode-*/result.json'))),native_observation_profiles=len(load('observability',[])),supplementary_session_closure_profiles=len(load('session-closure',[])),supplementary_matched_outage_controls=len(load('matched-collector-outage',[])),final=bool(scores.get('execution_complete_in_available_environment')),scope='Only pinned OpenClaw/Hermes Linux native CLI and complete Gateway. Two-product relative grades; no five-family normalization. Unfinished criteria are never coerced to 中. Architecture explanation author-reviewed, colleague review/sign-off pending.')
 save(R/'results/eleven-dimensions-review.json',dict(status=status,rows=rows))
 with (R/'results/eleven-dimensions-review.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.writer(f);w.writerow(['维度','OpenClaw档位','OpenClaw一句话','Hermes档位','Hermes一句话','可判别权重','净优势区间','证据'])
  for x in rows:w.writerow([x['dimension'],x['openclaw_grade'] or '未定档',x['openclaw_reason'],x['hermes_grade'] or '未定档',x['hermes_reason'],x['coverage'],str(x['interval']),' | '.join(x['evidence'])])
 esc=html.escape;table=[]
 for x in rows:
  cells=[]
  for f in ['openclaw','hermes']:
   grade=x[f+'_grade'] or '未定档';cells.append('<td><b class="g'+esc(grade)+'">'+esc(grade)+'：</b>'+esc(x[f+'_reason'])+'</td>')
  ev='<br>'.join('<a href="../'+esc(p)+'">'+esc(p.removeprefix('results/'))+'</a>' for p in x['evidence']) or '尚未纳入完整验收'
  details=''.join('<li>'+esc(c['label'])+'（'+str(c['weight'])+'%）：'+esc(c['measurement_definition'])+'</li>' for c in x['criteria'])
  architecture=load('architecture-review-notes',{}).get(x['id'],{})
  explanation=''.join('<p><b>'+esc(k)+'：</b>'+esc(architecture[k])+'</p>' for k in ['做法差异','设计与取舍','实测与边界'] if k in architecture)
  if architecture.get('source_claims'):explanation+='<p>固定源码索引：'+esc('、'.join(architecture['source_claims']))+'；见<a href="../evidence/source-architecture-index.json">带SHA与行号的源码依据</a>。</p>'
  details+=explanation
  table.append('<tr><th>'+esc(x['dimension'])+'</th>'+''.join(cells)+'<td>可判别 '+str(x['coverage'])+'%<br>净优势 '+esc(str(x['interval']))+'<details><summary>判据与证据</summary><ul>'+details+'</ul>'+ev+'</details></td></tr>')
 body='''<!doctype html><meta charset="utf-8"><title>OpenClaw / Hermes 11维证据对比</title><style>body{font:16px/1.65 system-ui,sans-serif;max-width:1450px;margin:35px auto;padding:0 22px;color:#17212d}table{border-collapse:collapse;width:100%;table-layout:fixed}th,td{border:1px solid #ccd4dc;padding:16px;vertical-align:top}thead{background:#edf1f5}th:first-child{width:12%}td:last-child{width:23%;font-size:13px}details{margin-top:10px}a{overflow-wrap:anywhere;color:#1954a6}.g强{color:#11754c}.g弱{color:#b42318}.g中{color:#805800}.g未定档{color:#68737d}.notice{background:#f3f6fa;padding:15px;border-left:4px solid #6687aa}li{margin-bottom:9px}</style><h1>OpenClaw / Hermes：11维证据对比</h1>'''
 body+='<p class="notice">'+('本环境已完成实验的审阅稿；不可用及未能定档的项目明确保留。' if status['final'] else '进行中快照，尚非完整结论。')+'OpenClaw 2026.10.6 / Hermes v0.22.5；真实生成推理统一 DeepSeek Flash high。已完成真实首次任务 '+str(status['formal_completed'])+'/48、文档走查 '+str(len(attacks))+'/16、复用 '+str(status['reuse_episodes_completed'])+'/36。只比较两产品；未测平台不计失败，也不填中。</p><p>强/弱表示在冻结用例、权重和对手集合中的相对优势；中可表示已验证的相当或不同优势相互抵消。完整判据见<a href="../../oc-hermes-formal-design-20261024/protocol_v1.json">冻结协议</a>；同事审核尚未签认。</p><table><thead><tr><th>维度</th><th>OpenClaw</th><th>Hermes</th><th>覆盖与审核入口</th></tr></thead><tbody>'+''.join(table)+'</tbody></table>'
 body+='<p class="notice">补充机制核验：'+str(status['supplementary_session_closure_profiles'])+'个同会话片段关闭能力正控、'+str(status['supplementary_matched_outage_controls'])+'个同原始单元的工具阶段断采对照；不增加原始独立样本数。<a href="session-closure-native-audit.json">完整本地轨迹证据</a>；<a href="matched-collector-native-audit.json">同一拒收执行记录的补送核验</a>。审计主评分按冻结共同合同，具体授权范围的严格需求另见<a href="observability-rubric-sensitivity.json">已披露的口径敏感性</a>。费用按API用量日志和固定单价估算，不宣称已逐笔核对服务商账单。</p>'
 body+='<p class="notice">支持语句采用“架构机制→有条件的典型表现”。†表示源码已确认执行结构，但对内存、首字／吞吐差异的主导贡献尚未独立归因；MCP锁的串行效应已有直接对照。资源维度默认综合未定，预登记的内存优先口径为OpenClaw弱／Hermes强；工作线程共享解释器不等于所有负载吞吐都更高，独立JS引擎也不意味着全部数据复制。<a href="architecture-causal-interpretation.json">因果解释与证据强度</a>。</p>'
 body+='<p><a href="OpenClaw_Hermes_11维实验对比.xlsx">下载三列表格与审核说明（Excel）</a>；<a href="eleven-dimensions-review.csv">CSV</a>；<a href="architecture-review-notes.json">11维架构分析</a>；<a href="scorecard-method.html">完整评分标准</a>。</p>'
 (R/'results/eleven-dimensions-review.html').write_text(body)
 print('REVIEW_MATRIX_UPDATED',status)
if __name__=='__main__':main()
