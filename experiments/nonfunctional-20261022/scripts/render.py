import html,json,zipfile
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
R=Path(__file__).resolve().parents[1];summary=json.loads((R/'results/summary.json').read_text());metrics=[m for m in summary['metrics']if m['different']];FONT=FontProperties(fname='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc');plt.rcParams.update({'font.family':FONT.get_name(),'axes.unicode_minus':False});(R/'charts').mkdir(exist_ok=True)
cards=[]
for m in metrics:
    values=[m['values'][f]for f in ['openclaw','hermes']];fig,ax=plt.subplots(figsize=(7.4,4.9));bars=ax.bar(['OpenClaw','Hermes Agent'],values,color=['#2563eb','#10a88b'],width=.5);mx=max(values)or 1;ax.set_ylim(0,mx*1.28);ax.spines[['top','right']].set_visible(False);ax.set_ylabel(m['unit'],fontproperties=FONT);ax.set_title(m['dimension']+'\n'+m['label'],fontproperties=FONT,fontsize=12,pad=14);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    for b,v in zip(bars,values):
        digits=2 if m['unit']=='请求/秒'else 1 if m['unit']=='ms'else 0;ax.text(b.get_x()+b.get_width()/2,v+mx*.035,f'{v:.{digits}f}',ha='center',fontsize=12)
    sample=' / '.join(f'{f}: n={m["n"][f]}'for f in ['openclaw','hermes']);fig.text(.5,.015,sample,ha='center',fontsize=8,color='#64748b');fig.tight_layout(rect=[0,.04,1,1])
    for extension in ['png','svg','pdf']:fig.savefig(R/f'charts/{m["id"]}.{extension}',dpi=170,bbox_inches='tight')
    plt.close(fig)
    cards.append('<section><h2>'+html.escape(m['label'])+'</h2><p><b>机制点：</b>'+html.escape(m['mechanism'])+'</p><p><b>实验设计：</b>'+html.escape(m['design'])+'</p><img src="charts/'+m['id']+'.png"><p class="note">'+html.escape(m['note'])+'</p></section>')
doc='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OpenClaw 与 Hermes 非功能实测</title><style>body{max-width:1050px;margin:32px auto;padding:0 24px;font:16px/1.7 system-ui,sans-serif;color:#172033;background:#f5f7fb}section{background:white;border:1px solid #dfe5ee;padding:24px;border-radius:12px;margin:24px 0}img{width:100%;height:auto}.note{font-size:13px;color:#64748b}h1,h2{line-height:1.4}</style><h1>OpenClaw 与 Hermes：非功能实测</h1><p>已测9个维度。以下只展示本轮数值不同的指标；这是一批固定配置下的小样本实验。真实HTTP服务接入相同DeepSeek模型；故障由入口受控注入，工具进程与文件操作实际执行。Token按服务商返回值统计，不等于实际账单。</p><p><a href="results/chart-data.csv">下载作图CSV</a> · <a href="results/summary.json">完整结果与验收检查</a></p>'+''.join(cards)+'</html>'
(R/'report.html').write_text(doc)
with zipfile.ZipFile(R/'nonfunctional-results.zip','w',zipfile.ZIP_DEFLATED)as z:
    for folder in ['scripts','results','charts']:
        for p in(R/folder).rglob('*'):
            if p.is_file()and '__pycache__'not in p.parts:z.write(p,p.relative_to(R))
    for p in(R/'raw').glob('*.json'):
        # Native backup records may contain machine identities; keep only measurements in the portable bundle.
        if p.name.startswith('backup'):
            records=json.loads(p.read_text());safe=[{k:v for k,v in d.items()if k in['framework','sample','warmup','backup_ms','restore_ms','archive_bytes','correct_files','expected_files']}for d in records];z.writestr('raw/'+p.name,json.dumps(safe,ensure_ascii=False))
        else:z.write(p,p.relative_to(R))
    z.write(R/'report.html','report.html');z.write(R/'RUNBOOK.md','RUNBOOK.md')
print(json.dumps({'charts':len(metrics),'artifacts':['report.html','nonfunctional-results.zip','results/chart-data.csv']},ensure_ascii=False))
