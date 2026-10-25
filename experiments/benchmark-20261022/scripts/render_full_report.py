"""Render one scoped, evidence-backed comparison for every measured technical row."""
import argparse,csv,html,json,math,shutil,statistics,textwrap
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

ROOT=Path(__file__).resolve().parents[1]
FONT=FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family':FONT.get_name(),'axes.unicode_minus':False,'font.size':10})
COLORS={'openclaw':'#2563eb','hermes':'#ea580c'}
LABELS={'openclaw':'OpenClaw','hermes':'Hermes'}
BASE={6:'06-sandbox-ready.png',8:'08-mcp-scheduling.png',23:'23-skills-catalog.png',26:'26-quota-enforcement.png'}
BRIEF={1:'会话键共享与隔离；不是完整IM路由系统。',2:'同机两个独立SSH端点；不代表跨地域云调度。',3:'原生发送者准入决策；不代表完整安全审计。',4:'原生工作目录路径归属；不等同沙箱权限隔离。',5:'长工具输出预算与原文保留；不代表压缩后回答准确率。',7:'10个真实DeepSeek数据处理任务，独立核验最终JSON产物。',9:'固定计划、单个子任务派生与完成；不代表自主团队协作质量。',10:'原生定时任务持久化生命周期；不代表任意长任务恢复。',11:'相同5技能、10个中文语义请求；核验技能专属随机标记。',12:'3个技能×6条生命周期断言；不是生态规模或学习效果。',13:'stdio MCP新会话与内容往返；不代表全部消息协议。',14:'原生记忆持久化CRUD；不是长期语义检索或跨会话问答准确率。',15:'10组当前/过期本地文档问题；事实、来源、合计值同时核验。',16:'10张相同PNG×3字段，同一DeepSeek模型；仅静态图像输入链路。',17:'原生Retry-After解析；不代表完整重试/回退可用性。',18:'同机双SSH端点资源访问；不代表物理分布式伸缩。',19:'原生显式deny优先级；命令未实际执行，不代表综合安全水平。',20:'源码入口预热后完整无工具回合CPU（10ms计量粒度）；本地固定响应，非发行版性能。',21:'实际HTTP入口→原生工具→回复；不代表全部网关入口。',22:'固定DOM操作计划与独立服务端验收；不代表自主视觉驾驶成功率。',24:'已捕获文件SHA恢复；新增文件处理、进程内存恢复另论。',25:'独立本地兼容端点协议用例；不代表推理引擎速度或模型质量。'}

def escape(value):return html.escape(str(value))
def percent_data(data):
    values=data.get('values',[])
    if not values:raise ValueError('Missing actual observations')
    if any(v not in [0,1] for v in values):raise ValueError('Pass rate needs actual binary outcomes')
    if data.get('total')!=len(values) or data.get('passed')!=sum(values):raise ValueError('Outcome count mismatch')
    return 100*sum(values)/len(values)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--allow-partial',action='store_true');args=parser.parse_args()
    coverage=json.loads((ROOT/'results/coverage.json').read_text());names={r['id']:r['item'] for r in coverage['rows']}
    measurements={int(p.stem.rsplit('-',1)[1]):json.loads(p.read_text()) for p in (ROOT/'results').glob('extended-row-*.json')}
    observed=set(BASE)|set(measurements)
    if not args.allow_partial and observed!=set(range(1,27)):raise ValueError(f'Missing rows: {sorted(set(range(1,27))-observed)}')
    summary=[];cards=[];table=[];flat_rows=[]
    first_summary=json.loads((ROOT/'results/summary.json').read_text())
    for row in range(1,27):
        if row not in observed:continue
        if row in BASE:
            chart=BASE[row];entry={'row':row,'title':names[row],'scope':'详见图中具体场景、条件和测量边界。','limitations':[]}
            groups=[x for x in first_summary if x['row']==row]
            for x in groups:summary.append({'row':row,'metric':x['metric'],'framework':x['framework'],'condition':x['condition'],'n':x['n'],'value':x['median'],'unit':x['unit'],'passed':x['passed'],'total':x['total'],'scope':x['scope']})
            if row==6:
                labels={f:'冷 '+format(next(x['median'] for x in groups if x['framework']==f and x['metric']=='cold_create_and_command'),'.1f')+' / 热 '+format(next(x['median'] for x in groups if x['framework']==f and x['metric']=='warm_reattach_and_command'),'.1f')+' ms' for f in LABELS};metric='沙箱就绪与首条命令';count='每条件30次'
            elif row==8:
                labels={f:format(next(x['median'] for x in groups if x['framework']==f and x['metric']=='one_mcp_server_four_call_batch'),'.1f')+' ms' for f in LABELS};metric='同MCP连接4工具批次';count='每框架1会话30批'
            elif row==23:
                labels={f:'冷 '+format(next(x['median'] for x in groups if x['framework']==f and x['metric']=='catalog_cold' and x['condition']=='500 skills'),'.2f')+' / 热 '+format(next(x['median'] for x in groups if x['framework']==f and x['metric']=='catalog_warm' and x['condition']=='500 skills'),'.3f')+' ms' for f in LABELS};metric='500技能目录缓存';count='每条件30次，另有10/100技能分组'
            else:labels={f:'CPU/内存/PID各3/3' for f in LABELS};metric='容器资源配额实际约束';count='每资源每框架3次'
            evidence='results/'+{6:'sandbox-samples.json',8:'mcp-samples.json',23:'skills-samples.json',26:'quota-samples.json'}[row]
        else:
            entry=measurements[row]
            if entry.get('status')!='measured':raise ValueError(f'Row{row} not measured')
            chart=f'{row:02d}-comparison.png';metric=entry['metric'];unit=entry['unit'];labels={};counts=[]
            fig,ax=plt.subplots(figsize=(9,5.7))
            for index,framework in enumerate(LABELS):
                data=entry['frameworks'][framework];values=data['values']
                if not values or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in values):raise ValueError('Missing/nonfinite measurement')
                if unit=='%':
                    value=percent_data(data);text=f"{value:.0f}%（{data['passed']}/{data['total']}）";error=None;labels[framework]=f"{data['passed']}/{data['total']}"
                else:
                    value=statistics.median(values);q=statistics.quantiles(values,n=4,method='inclusive') if len(values)>1 else [value]*3;error=[[value-q[0]],[q[2]-value]];text=(f'{value:.0f} {unit}' if row==20 else f'{value:.3f} {unit}');labels[framework]=text
                ax.bar(index,value,.55,color=COLORS[framework],yerr=error,capsize=4)
                ax.annotate(text,(index,value+(error[1][0] if error else 0)),xytext=(0,8),textcoords='offset points',ha='center',fontproperties=FONT,fontsize=11)
                counts.append(str(data.get('total',len(values))))
                summary.append({'row':row,'metric':metric,'framework':framework,'condition':'本次限定场景','n':len(values),'value':value,'unit':unit,'passed':data.get('passed',''),'total':data.get('total',len(values)),'scope':entry['scope']})
            ax.set_title(f'{names[row]}\n{metric}',fontproperties=FONT,fontsize=14,pad=16)
            ax.set_xticks([0,1],list(LABELS.values()))
            ax.set_ylabel('固定用例通过率（%）' if unit=='%' else f'中位数（{unit}）',fontproperties=FONT)
            ax.set_ylim(bottom=0,top=115 if unit=='%' else None);ax.margins(y=.22);ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
            foot=BRIEF.get(row,entry['scope'])+'\n两边样本数：'+' / '.join(counts)+('；数值误差线为四分位区间。' if unit!='%' else '；仅代表所列固定用例，不是全领域能力分数。')
            fig.text(.5,.035,foot,ha='center',fontproperties=FONT,fontsize=8,color='#475569')
            fig.tight_layout(rect=[0,.11,1,1])
            for ext in ['png','svg','pdf']:fig.savefig(ROOT/f'charts/{row:02d}-comparison.{ext}',dpi=180)
            plt.close(fig);count=' / '.join(counts);evidence=f'results/extended-row-{row:02d}.json'
        limit_html=''.join('<li>'+escape(x)+'</li>' for x in entry.get('limitations',[]))
        cards.append(f'<section id="row-{row:02d}"><h2>{escape(names[row])}</h2><img loading="lazy" src="charts/{chart}" alt="{escape(names[row])}"><p><b>测量范围：</b>{escape(entry["scope"])}</p><ul>{limit_html}</ul><p><a href="{evidence}">逐项数据与证据</a> · <a href="charts/{chart.replace(".png",".svg")}">SVG</a> · <a href="charts/{chart.replace(".png",".pdf")}">PDF</a></p></section>')
        flat_rows.append({'row':row,'item':names[row],'metric':metric,'openclaw':labels['openclaw'],'hermes':labels['hermes'],'samples':count,'scope':entry['scope'],'limitations':' | '.join(entry.get('limitations',[])),'chart':'charts/'+chart,'evidence':evidence})
        table.append(f'<tr><td><a href="#row-{row:02d}">{escape(names[row])}</a></td><td>{escape(metric)}</td><td>{escape(labels["openclaw"])}</td><td>{escape(labels["hermes"])}</td><td>{escape(count)}</td></tr>')
    with (ROOT/'results/technical-map-26.csv').open('w',newline='',encoding='utf-8-sig') as output:
        writer=csv.DictWriter(output,fieldnames=list(flat_rows[0]));writer.writeheader();writer.writerows(flat_rows)
    with (ROOT/'results/all-26-summary.csv').open('w',newline='',encoding='utf-8-sig') as output:
        writer=csv.DictWriter(output,fieldnames=list(summary[0]));writer.writeheader();writer.writerows(summary)
    (ROOT/'results/all-26-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    for row in coverage['rows']:
        if row['id'] in observed:row.update({'status':'baseline_measured','evidence':[f'results/extended-row-{row["id"]:02d}.json'] if row['id'] not in BASE else ['results/'+{6:'sandbox-samples.json',8:'mcp-samples.json',23:'skills-samples.json',26:'quota-samples.json'}[row['id']]]});row.pop('remaining',None)
    (ROOT/'results/coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2))
    intro=f'<h1>OpenClaw / Hermes：{len(observed)}/26项基线实测</h1><div class="note">每项都有实际双边执行记录与柱状图。这里比较每项的一个明确限定场景：通过率不等于完整领域能力，许多基础契约两边都通过；没有把26项混成总分。真实模型任务统一使用deepseek-flash。组件实验、固定脚本模型和真实模型任务分别标明。</div>'
    method='<h2>如何读这些结果</h2><p>01/03/04/05/10/12/14/17/19主要验证原生组件契约；02/09/13/18/21/22为原生集成链路；07/11/15/16使用真实DeepSeek。06/08/23为耗时场景，26为容器资源约束。20明确采用其图中给出的资源测量边界。固定通过率测试不用于证明两套系统整体等价。</p><p>OpenClaw固定commit1b58cb9a1b4f4353e1add63c8506db4d890962e8；Hermes固定commit5b147ab036d6d19131bff8d20701b5001eab844a。SSH端点同机，浏览器按固定DOM计划，MCP仅本次传输与连接设置；未外推物理多机伸缩、自主视觉驾驶或推理引擎TPS。完整源码冷启动RSS未作为生产资源排名。</p><p>DeepSeek密钥保存在实验目录外，报告与数据包不含密钥。真实模型费用未按框架默认0价格计算；只保留实际Token用量，不把缺失价格当作免费。</p>'
    doc='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>26项基线实测</title><style>body{font:16px/1.7 system-ui,sans-serif;color:#172033;background:#f8fafc;max-width:1200px;margin:32px auto;padding:0 24px}h1,h2{line-height:1.4}.note{background:#eaf1ff;padding:20px;border-radius:10px}section{background:white;border:1px solid #dbe3ed;border-radius:12px;margin:30px 0;padding:22px;scroll-margin-top:20px}section img{width:100%;height:auto}table{border-collapse:collapse;width:100%;background:white;font-size:13px}th,td{border:1px solid #dbe3ed;padding:8px;text-align:left}a{color:#2563eb}p,li{overflow-wrap:anywhere}</style>'+intro+'<p><a href="results/technical-map-26.csv">下载26项表格CSV</a> · <a href="results/all-26-summary.csv">下载各条件统计CSV</a> · <a href="results/coverage.json">26项状态</a> · <a href="results/environment-final.json">环境与版本</a> · <a href="full-results.zip">数据与复跑脚本包</a></p>'+method+'<h2>全表结果</h2><table><tr><th>项目</th><th>本次实测指标</th><th>OpenClaw</th><th>Hermes</th><th>样本数/单位见图</th></tr>'+''.join(table)+'</table>'+''.join(cards)+'</html>'
    (ROOT/'report.html').write_text(doc)
    print(json.dumps({'rows_with_charts':len(observed),'summary_rows':len(summary),'report':str(ROOT/'report.html')},ensure_ascii=False))

if __name__=='__main__':main()
