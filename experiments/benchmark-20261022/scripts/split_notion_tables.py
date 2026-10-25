"""Prepare a mechanism-only table and a separate one-test-per-row comparison page."""
import csv,io,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'results'
edit=json.loads((R/'notion-quantification-edit.json').read_text())
source=(R/'notion-split-current-source.txt').read_text()
content=re.search(r'<content>\n([\s\S]*?)\n</content>',source).group(1)
old_table=re.search(r'<table\b[\s\S]*?</table>',content).group()
prefix=content[:content.index(old_table)].strip()
suffix=content[content.index(old_table)+len(old_table):].strip()
file_block=re.search(r'<file\b[^>]*?\s*/>',suffix).group()
rows=list(re.finditer(r'<tr\b[^>]*>([\s\S]*?)</tr>',old_table))
def normalize(s):
    return re.sub(r'<code>([\s\S]*?)</code>',lambda m:'`'+m[1]+'`',s.replace('<b>','**').replace('</b>','**')).replace('<br />','<br>')
new_rows=[]
for index,rm in enumerate(rows):
    row=rm.group()
    if index:
        cells=list(re.finditer(r'<td\b[^>]*>([\s\S]*?)</td>',row))
        for col in [3,4,5]:
            cell=cells[col];parts=re.split(r'<br\s*/?>\s*<br\s*/?>',cell[1].strip());kept=[]
            for part in parts:
                if re.match(r'<b>(本轮已测范围|可比较主指标)',part):continue
                part=re.split(r'<br\s*/?>\s*<b>测试 T\d\d\.\d',part)[0]
                if index==6 and part.startswith('<b>启动延迟</b>'):
                    part='<b>启动延迟</b>：见测试表 T06.5。'
                if index==16 and part.startswith('<b>识别效果</b>'):
                    part='<b>识别效果</b>：见测试表 T16.4。'
                if index==22 and part.startswith('<b>实际任务效果</b>'):
                    part='<b>实际任务效果</b>：见测试表 T22.5。'
                if index==20 and part.startswith('<b>框架资源怎样计量</b>'):
                    part='<b>框架资源怎样计量</b>：模型推理可运行在外部服务，框架与模型资源分别计量；实测见测试表 T20.4。'
                if part.strip():kept.append(part.strip())
            cleaned='\n'+'<br><br>'.join(normalize(x) for x in kept)+'\n'
            row=row.replace(cell.group(),cell.group().replace(cell[1],cleaned,1),1)
    new_rows.append(normalize(row))
mechanism_table=old_table
for rm,new in zip(rows,new_rows):mechanism_table=mechanism_table.replace(rm.group(),new,1)
assert len(new_rows)==27 and '测试 T' not in mechanism_table
assert '本轮已测范围' not in mechanism_table and '可比较主指标' not in mechanism_table
links=lambda t:set(re.findall(r'https?://[^)<>\s]+',t))
assert links(old_table)<=links(mechanism_table)

grouped={}
for item in edit['subtests']:
    grouped.setdefault(item['test_id'],{})[item['framework']]=item
assert len(grouped)==107
all_names={int(r['id']):r['item'] for r in json.loads((R/'coverage.json').read_text())['rows']}
headers=['比较项','测试ID／分项','测试方法','指标（单位）','OpenClaw','Hermes Agent','覆盖状态']
test_rows=[];flat=[]
for test_id,pair in grouped.items():
    oc=pair['OpenClaw'];he=pair['Hermes Agent']
    for key in ['statement','test','metric','status']:assert oc[key]==he[key],(test_id,key)
    i=int(oc['item'])
    values=[all_names[i],test_id+'<br>'+oc['statement'],oc['test'],oc['metric'],oc['result'],he['result'],oc['status']]
    test_rows.append('<tr>\n'+'\n'.join('<td>'+v+'</td>' for v in values)+'\n</tr>')
    flat.append(dict(zip(headers,[all_names[i],test_id+' '+oc['statement'],oc['test'],oc['metric'],oc['result'],he['result'],oc['status']])))
header='<tr color="gray_bg">\n'+'\n'.join('<td>**'+h+'**</td>' for h in headers)+'\n</tr>'
test_table='<table header-row="true">\n<colgroup>\n'+''.join(f'<col width="{w}" />\n' for w in [150,190,350,300,330,330,110])+'</colgroup>\n'+header+'\n'+'\n'.join(test_rows)+'\n</table>'
intro='''机制说明：<mention-page url="https://app.notion.com/p/4002817dde3b817a895ed945e0d0aca8">按技术图谱对比</mention-page>。这里按“一项测试一行”列方法、指标和双边结果，原214个逐框架条目合并为107行，测试ID保持不变。

**覆盖状态**：已测＝该限定场景有实测；部分已测＝只覆盖原机制的一部分；待测＝暂无实数；不适用＝当前机制不承担该项能力，不填0分或0ms。

**统计口径**：通过率保留分子/分母；字段、断言、工具批次与独立任务不是同一样本单位，同组数据重复引用不增加样本数。耗时均注明中位数、单位和样本数。当前仅比较OpenClaw／Hermes。

**实验版本**：OpenClaw [1b58cb9](https://github.com/openclaw/openclaw/tree/1b58cb9a1b4f4353e1add63c8506db4d890962e8)；Hermes [5b147ab](https://github.com/NousResearch/hermes-agent/tree/5b147ab036d6d19131bff8d20701b5001eab844a)。日期2026-10-22。真实模型题用deepseek-flash、thinking关闭、temperature0；组件/协议题用固定测试数据或脚本响应。

**重要边界**：T10的13/13只验证Cron，不证明任务板/依赖图；T22为固定DOM操作，不证明自主视觉驾驶；T25是脚本协议端点，不是实际推理引擎；T20是源码API最小回合CPU，不是发行版总体资源。冷目录缓存指应用缓存冷、OS文件缓存热。
'''
footer='''

## 补充行级基线

T10补充基线为原生Cron创建、查询、暂停、恢复、修改、删除及重载，OpenClaw／Hermes均13/13；它不覆盖T10.1—T10.5中的任务板、优先级、检查点和失败恢复。其余实数已放到对应测试行。

## CSV明细

原214行逐框架CSV保留，便于筛选和复用；上表将相同测试ID的两边结果并排展示。
'''+file_block
new_page=intro+'\n'+test_table+footer
buf=io.StringIO();writer=csv.DictWriter(buf,fieldnames=headers);writer.writeheader();writer.writerows(flat)
(R/'notion-tests-side-by-side.csv').write_text(buf.getvalue(),encoding='utf-8-sig')
draft={'old_table':old_table,'new_mechanism_table':mechanism_table,'old_prefix':prefix,'old_suffix':suffix,'new_page_content':new_page,'test_table':test_table,'file_block':file_block}
(R/'notion-split-draft.json').write_text(json.dumps(draft,ensure_ascii=False,indent=2))
(R/'notion-test-page-draft.txt').write_text(new_page)
print(json.dumps({'mechanism_chars_before':len(old_table),'mechanism_chars_after':len(mechanism_table),'original_rows':len(rows)-1,'new_test_rows':len(test_rows),'new_test_columns':len(headers),'new_page_chars':len(new_page),'maximum_result_chars':max(len(r[h]) for r in flat for h in ['OpenClaw','Hermes Agent'])},ensure_ascii=False))
