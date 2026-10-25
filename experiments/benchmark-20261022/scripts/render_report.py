"""Summarize verified measurements, chart medians, and publish a local HTML artifact."""
import collections
import csv
import hashlib
import html
import json
from pathlib import Path
import random
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

ROOT = Path(__file__).resolve().parents[1]
FONT = FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family':FONT.get_name(),'axes.unicode_minus':False,'font.size':10})
COLORS = {'openclaw':'#2563eb','hermes':'#ea580c'}
LABELS = {'openclaw':'OpenClaw','hermes':'Hermes'}
summary=[]

def summarize(row,metric,framework,condition,values,correct,scope,unit='ms'):
    median=statistics.median(values)
    seed=int(hashlib.sha256(f'{row}:{metric}:{framework}:{condition}'.encode()).hexdigest()[:12],16)
    rng=random.Random(seed)
    boot=sorted(statistics.median(rng.choices(values,k=len(values))) for _ in range(2000))
    low,high=boot[49],boot[1949]
    result={'row':row,'metric':metric,'framework':framework,'condition':condition,'n':len(values),'median':median,'mean':statistics.mean(values),'ci95_low':low,'ci95_high':high,'unit':unit,'passed':sum(correct),'total':len(correct),'scope':scope,'q25':statistics.quantiles(values,n=4,method='inclusive')[0],'q75':statistics.quantiles(values,n=4,method='inclusive')[2]}
    summary.append(result)
    return result

def style(ax,title,ylabel):
    ax.set_title(title,fontproperties=FONT,pad=14)
    ax.set_ylabel(ylabel,fontproperties=FONT)
    ax.spines[['top','right']].set_visible(False)
    ax.grid(axis='y',alpha=.18)
    ax.set_axisbelow(True)
    ax.set_ylim(bottom=0)

def main():
    files=[]
    skills=ROOT/'results/skills-samples.json'
    if skills.exists():
        payload=json.loads(skills.read_text())
        rows=payload['samples']
        if not all(r['correct'] for r in rows):
            raise RuntimeError('Skill validation failed; refusing performance chart')
        groups=collections.defaultdict(list)
        for row in rows:groups[row['metric'],row['framework'],row['size']].append(row)
        fig,axes=plt.subplots(1,2,figsize=(12,4.8))
        for ax,metric,title in zip(axes,['catalog_cold','catalog_warm'],['应用目录缓存冷','应用目录缓存热']):
            for position,framework in enumerate(['openclaw','hermes']):
                heights=[];lower=[];upper=[]
                for size in [10,100,500]:
                    sample=groups[metric,framework,size]
                    stats=summarize(23,metric,framework,f'{size} skills',[r['duration_ms'] for r in sample],[r['correct'] for r in sample],'Native catalog API; imports excluded, OS file cache warm')
                    heights.append(stats['median']);lower.append(stats['median']-stats['ci95_low']);upper.append(stats['ci95_high']-stats['median'])
                bars=ax.bar([x+(position-.5)*.36 for x in range(3)],heights,.34,label=LABELS[framework],color=COLORS[framework],yerr=[lower,upper],capsize=3)
                for bar,value in zip(bars,heights):ax.annotate(f'{value:.3f}',(bar.get_x()+bar.get_width()/2,bar.get_height()),xytext=(0,6),textcoords='offset points',ha='center',fontsize=8)
            style(ax,title,'目录发现耗时中位数（毫秒，越低越好）')
            ax.set_xticks(range(3),['10','100','500'])
            ax.set_xlabel('技能数量；单份 SKILL.md 为 5,011 字节',fontproperties=FONT)
            ax.legend(frameon=False)
            ax.margins(y=.22)
        fig.suptitle('第23项：原生技能目录接口实测',fontproperties=FONT,fontsize=16)
        fig.text(.5,.015,'每组 n=30；误差线为中位数的95% bootstrap区间。固定源码接口，不代表完整 Agent/Gateway 延迟。',ha='center',fontproperties=FONT,fontsize=9,color='#475569')
        fig.tight_layout(rect=[0,.05,1,.94])
        for ext in ['png','svg','pdf']:fig.savefig(ROOT/f'charts/23-skills-catalog.{ext}',dpi=180)
        plt.close(fig)
        files.append(('23-skills-catalog.png','第23项：原生技能目录发现'))
    sandbox=ROOT/'results/sandbox-samples.json'
    if sandbox.exists():
        rows=json.loads(sandbox.read_text())['samples']
        if not all(r['correct'] for r in rows):raise RuntimeError('Invalid sandbox results')
        fig,ax=plt.subplots(figsize=(8,4.8))
        for position,framework in enumerate(['openclaw','hermes']):
            heights=[];lower=[];upper=[]
            for metric in ['cold_create_and_command','warm_reattach_and_command']:
                group=[r for r in rows if r['framework']==framework and r['metric']==metric]
                stats=summarize(6,metric,framework,metric,[r['duration_ms'] for r in group],[r['correct'] for r in group],'Native sandbox backend in source mode; image preloaded; framework-specific preparation included')
                heights.append(stats['median']);lower.append(stats['median']-stats['ci95_low']);upper.append(stats['ci95_high']-stats['median'])
            bars=ax.bar([x+(position-.5)*.36 for x in range(2)],heights,.34,label=LABELS[framework],color=COLORS[framework],yerr=[lower,upper],capsize=3)
            for bar,value in zip(bars,heights):ax.annotate(f'{value:.1f}',(bar.get_x()+bar.get_width()/2,value),xytext=(0,5),textcoords='offset points',ha='center',fontsize=9)
        style(ax,'第06项：原生沙箱后端就绪并完成首条命令','耗时中位数（毫秒，越低越好）')
        ax.set_xticks([0,1],['容器不存在：创建并执行','容器已存在：重新连接并执行'],fontproperties=FONT)
        ax.legend(frameon=False);ax.margins(y=.2)
        fig.text(.5,.015,'每组n=30，预热5次；误差线为中位数95% bootstrap区间。源码模式；保留各后端自身初始化。',ha='center',fontproperties=FONT,fontsize=8,color='#475569')
        fig.tight_layout(rect=[0,.06,1,1])
        for ext in ['png','svg','pdf']:fig.savefig(ROOT/f'charts/06-sandbox-ready.{ext}',dpi=180)
        plt.close(fig);files.append(('06-sandbox-ready.png','第06项：沙箱后端就绪'))
    mcp=ROOT/'results/mcp-samples.json'
    if mcp.exists():
        rows=json.loads(mcp.read_text())['samples']
        if len(rows)!=60 or not all(r['correct'] for r in rows):raise RuntimeError('Invalid MCP batch observations')
        fig,axes=plt.subplots(1,2,figsize=(11,4.5))
        for position,framework in enumerate(['openclaw','hermes']):
            group=[r for r in rows if r['framework']==framework]
            stats=summarize(8,'one_mcp_server_four_call_batch',framework,'one server, 4 calls',[r['duration_ms'] for r in group],[r['correct'] for r in group],'Within-session actual tool phase; scripted plan; one stdio MCP connection')
            stats['ci95_low']=stats['ci95_high']=''
            bar=axes[0].bar(position,stats['median'],.55,color=COLORS[framework],yerr=[[stats['median']-stats['q25']],[stats['q75']-stats['median']]],capsize=4)
            axes[0].annotate(f"{stats['median']:.1f}",(position,stats['median']),xytext=(0,6),textcoords='offset points',ha='center')
            concurrency=statistics.median(r['max_overlap'] for r in group)
            axes[1].bar(position,concurrency,.55,color=COLORS[framework])
            axes[1].annotate(f'{concurrency:.0f}',(position,concurrency),xytext=(0,6),textcoords='offset points',ha='center')
            summary.append({'row':8,'metric':'batch_max_overlap','framework':framework,'condition':'one server, 4 calls','n':len(group),'median':concurrency,'mean':statistics.mean(r['max_overlap'] for r in group),'ci95_low':'','ci95_high':'','unit':'tools','passed':len(group),'total':len(group),'scope':'Observed overlap within one MCP connection; not a general parallelism score'})
        style(axes[0],'4个工具完成的实际执行窗口','耗时中位数（毫秒，越低越好）')
        style(axes[1],'批内最大同时执行数','实际并发数中位数')
        for ax in axes:
            ax.set_xticks([0,1],['OpenClaw','Hermes']);ax.margins(y=.2)
        axes[1].set_yticks(range(5))
        fig.suptitle('第08项：单个 MCP 连接内的工具调度',fontproperties=FONT,fontsize=15)
        fig.text(.5,.015,'每工具等待200ms；每框架1会话，5批预热＋30批采样；误差线为四分位区间，仅代表此连接场景。',ha='center',fontproperties=FONT,fontsize=9,color='#475569')
        fig.tight_layout(rect=[0,.06,1,.92])
        for ext in ['png','svg','pdf']:fig.savefig(ROOT/f'charts/08-mcp-scheduling.{ext}',dpi=180)
        plt.close(fig);files.append(('08-mcp-scheduling.png','第08项：单个MCP连接内的工具调度'))
    quota=ROOT/'results/quota-samples.json'
    if quota.exists():
        rows=json.loads(quota.read_text())['samples'];fig,ax=plt.subplots(figsize=(8,4.5))
        for position,framework in enumerate(['openclaw','hermes']):
            heights=[]
            for resource in ['cpu','memory','pids']:
                group=[r for r in rows if r['framework']==framework and r['resource']==resource]
                if not group:raise RuntimeError('Missing quota cases')
                heights.append(100*sum(r['correct'] for r in group)/len(group))
                summary.append({'row':26,'metric':'quota_enforced','framework':framework,'condition':resource,'n':len(group),'median':heights[-1],'mean':heights[-1],'ci95_low':'','ci95_high':'','unit':'%','passed':sum(r['correct'] for r in group),'total':len(group),'scope':'Native configured sandbox; actual kernel pressure. Functional cases, not a security score.'})
            bars=ax.bar([x+(position-.5)*.36 for x in range(3)],heights,.34,label=LABELS[framework],color=COLORS[framework])
            for bar,value in zip(bars,heights):ax.annotate(f'{value:.0f}%',(bar.get_x()+bar.get_width()/2,value),xytext=(0,5),textcoords='offset points',ha='center')
        style(ax,'第26项：容器资源配额实际生效','用例通过率（%）')
        ax.set_xticks(range(3),['CPU 限流','内存超额阻断','进程数上限'],fontproperties=FONT);ax.set_ylim(0,115);ax.legend(frameon=False)
        fig.text(.5,.01,'仅验证已配置的1 CPU / 512 MiB / 128 PID容器配额（禁swap，每类3次），不代表整个框架进程均受限或安全能力总分。',ha='center',fontproperties=FONT,fontsize=8)
        fig.tight_layout(rect=[0,.06,1,1])
        for ext in ['png','svg','pdf']:fig.savefig(ROOT/f'charts/26-quota-enforcement.{ext}',dpi=180)
        plt.close(fig);files.append(('26-quota-enforcement.png','第26项：配额实际生效'))
    if summary:
        with (ROOT/'results/summary.csv').open('w',newline='') as output:
            writer=csv.DictWriter(output,fieldnames=list(summary[0]));writer.writeheader();writer.writerows(summary)
        (ROOT/'results/summary.json').write_text(json.dumps(summary,indent=2))
    coverage=json.loads((ROOT/'results/coverage.json').read_text())
    charted={23} if skills.exists() else set()
    if sandbox.exists():charted.add(6)
    if quota.exists():charted.add(26)
    if mcp.exists():charted.add(8)
    for row in coverage['rows']:
        if row['id'] in charted:row['status']='pilot_measured'
    (ROOT/'results/coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2))
    table=''.join('<tr><td>'+html.escape(str(r['row']))+'</td><td>'+html.escape(r['metric'])+'</td><td>'+LABELS[r['framework']]+'</td><td>'+html.escape(str(r['condition']))+'</td><td>'+str(r['n'])+'</td><td>'+f"{r['median']:.4f}"+'</td><td>'+r['unit']+'</td></tr>' for r in summary)
    source=json.loads((ROOT/'results/environment-preflight.json').read_text())['sources']
    source_html=''.join('<li>'+LABELS[k]+': <code>'+v['commit']+'</code></li>' for k,v in source.items())
    image_html=''.join('<figure><img src="charts/'+f+'" alt="'+label+'"><figcaption>'+label+'</figcaption></figure>' for f,label in files)
    coverage_labels={'preparing':'准备中','real_model_smoke_passed':'真实模型接入验收通过，待扩展用例','requires_matched_deployment':'待统一持久运行环境后实测'}
    coverage_html=''.join('<tr><td>'+html.escape(r['item'])+'</td><td>'+('已有探索性实测图' if r['id'] in charted else coverage_labels.get(r['status'],'尚未测量'))+'</td></tr>' for r in coverage['rows'])
    real_pilot=ROOT/'results/real-pilot-results.json'
    real_html=''
    if real_pilot.exists():
        real=json.loads(real_pilot.read_text())
        real_rows=''.join('<tr><td>'+LABELS[r['framework']]+'</td><td>deepseek-flash</td><td>'+('通过' if r['correct'] else '未通过')+'</td></tr>' for r in real['records'])
        real_html='<h2>DeepSeek真实接入验收</h2><p>API密钥已安全配置。两边使用同一模型、关闭thinking、temperature0、输出上限4096，处理相同120行CSV，再独立校验result.json。每边目前仅1个样本，作为接入验收，不据此画成功率或耗时排名。源码初始化时间未作为生产性能。</p><table><tr><th>框架</th><th>模型</th><th>产物精确校验</th></tr>'+real_rows+'</table><p><a href="results/real-pilot-results.json">验收记录</a> · <a href="results/deepseek-config.json">无密钥的接入参数</a></p>'
    report='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>OpenClaw / Hermes 实验记录</title><style>body{font:16px/1.7 system-ui,sans-serif;max-width:1120px;margin:40px auto;padding:0 24px;color:#172033;background:#f8fafc}h1,h2{line-height:1.3}figure{margin:32px 0;background:white;border:1px solid #dbe3ed;border-radius:12px;padding:12px}img{width:100%;height:auto}figcaption{color:#64748b}table{border-collapse:collapse;width:100%;background:white;font-size:14px}td,th{border:1px solid #dbe3ed;padding:8px;text-align:left}code{overflow-wrap:anywhere}.note{background:#eaf1ff;padding:16px;border-radius:8px}a{color:#2563eb}</style><h1>OpenClaw / Hermes：第一批实际实验</h1><p class="note">这是固定源码版本、固定测试集的探索性实测。尚未测量的项目没有分数；脚本模型不是实际大模型，其Token与费用不能作为成本数据。26项全部完成前，不给框架总分或总排名。</p><h2>版本与环境</h2><ul>'''+source_html+'''</ul><p>Ubuntu 24.04，4个逻辑CPU，约7.4GiB物理内存。两套源码及状态独立；Docker为本任务单独安装和启动，未修改已有网关。镜像按digest固定。</p><h2>图表</h2>'''+image_html+'''<h2>测量边界</h2><p>第23项仅测原生技能目录接口，排除模块导入；冷指应用目录缓存未命中，操作系统文件缓存仍为热。OpenClaw使用新进程，Hermes清除原生目录缓存；OpenClaw容量显式设为1000，保证500个技能全部加载。技能正文读取接口不对称，因此读取数据保留在原始记录，不据此画直接胜负图。</p><p>第06项测原生后端准备并执行首条命令，容器创建与复用分别测量；共同镜像及资源配额，各自后端初始化与安全选项另有差异。源码模式可能包含TypeScript工作线程加载成本，发布包性能需单独复测。</p><p>第08项在每个框架的一个实际会话内，用本地脚本模型固定35批工具计划；前5批预热、后30批采样。每批4个独立工具通过同一stdio MCP连接执行。只计真实工具开始到结束的窗口；误差线为四分位区间，不表示跨会话置信区间，也不代表所有工具或多服务器条件下的并行能力。</p><p>第26项通过实际CPU忙循环、超额内存申请、进程创建验证内核限制，范围仅为对应沙箱容器。内存压力测试显式禁用swap；预检时两边允许额外swap，因此640MiB申请成功是符合配置的行为，原始预检记录仍保留。</p><h2>汇总数据</h2><p><a href="results/summary.csv">下载CSV</a> · <a href="results/skills-samples.json">技能逐次记录</a> · <a href="results/environment-preflight.json">初始环境预检</a> · <a href="results/environment-final.json">实际测量环境</a></p><table><thead><tr><th>条目</th><th>指标</th><th>框架</th><th>条件</th><th>样本数</th><th>中位数／通过率</th><th>单位</th></tr></thead><tbody>'''+table+'''</tbody></table>'''+real_html+'''<h2>26项覆盖状态</h2><table><thead><tr><th>比较项</th><th>状态</th></tr></thead><tbody>'''+coverage_html+'''</tbody></table></html>'''
    (ROOT/'report.html').write_text(report)
    print(json.dumps({'charts':len(files),'summary_rows':len(summary),'report':str(ROOT/'report.html')},ensure_ascii=False))

if __name__=='__main__':main()
