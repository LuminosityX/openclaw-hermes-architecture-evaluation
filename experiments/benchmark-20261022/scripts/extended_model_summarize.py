"""Independent semantic JSON and image-field verification for the real-model cases."""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
all_cases=json.loads((ROOT/'results/extended-model-cases.json').read_text())['cases']
titles={7:'Agent Loop',11:'意图识别',15:'知识管理'}
metrics={7:'固定结构化数据任务产物正确率',11:'技能语义路由命中率',15:'当前版本知识问答及证据一致率'}
scopes={7:'10项真实DeepSeek任务：数值汇总、最新版本记录选择、字符串转整数去重；后5项要求先执行会失败的文件检查，再产出结果并重查。最终result.json由独立代码与预设答案比对。',11:'5个相同合成技能、10种中文业务请求，通过各自原生技能目录/读取工具选择技能；检查技能专属随机marker及名称，不以仅口头宣称选中为准。',15:'40份当前/过期知识文档、10个双文档检索问题；检查事实、当前版本、两个来源路径与合计值。使用本地文件资料路径，不代表可选wiki插件或外部RAG服务。'}
for row in [7,11,15]:
    cases=[c for c in all_cases if c['row']==row]
    frameworks={};complete=True
    for framework in ['openclaw','hermes']:
        records=[]
        for case in cases:
            path=ROOT/f'raw/extended-models/{framework}-{case["case_id"]}.json'
            if not path.exists():complete=False;continue
            record=json.loads(path.read_text())
            workspace=Path(case['workspaces'][framework]);actual=None
            try:actual=json.loads((workspace/case['output_file']).read_text())
            except (ValueError,OSError):pass
            # Key order and whitespace are not semantic differences.
            record['independent_correct']=actual==case['expected']
            record['independent_actual']=actual
            records.append(record)
        values=[int(x['independent_correct']) for x in records]
        frameworks[framework]={'values':values,'passed':sum(values),'total':len(values),'entrypoints':['agentExecCommand' if framework=='openclaw' else 'AIAgent.run_conversation'],'evidence':[f'raw/extended-models/{framework}-{c["case_id"]}.json' for c in cases],'case_results':[{'case_id':x['case_id'],'correct':x['independent_correct']} for x in records]}
    if complete:
        payload={'row':row,'title':titles[row],'metric':metrics[row],'unit':'%','direction':'higher','scope':scopes[row],'limitations':['固定小样本任务集，每框架10题；不推断任意复杂任务成功率。','模型统一deepseek-flash，thinking关闭、temperature0、单次输出上限1536；两边使用各自原生工具/系统上下文。','源码初始化及完整耗时不作生产性能排名。','本指标独立核验最终产物，不据此判断每条中途指令遵循率或所有故障恢复能力。'],'status':'measured','frameworks':frameworks,'model':'deepseek-flash','independent_verification':True}
        (ROOT/f'results/extended-row-{row:02d}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
        print(json.dumps({'row':row,'results':{f:[x['passed'],x['total']] for f,x in frameworks.items()}}))

spec=json.loads((ROOT/'results/extended-vision-cases.json').read_text())
frameworks={};complete=True
for framework in ['openclaw','hermes']:
    path=ROOT/f'raw/extended-models/vision-{framework}.json'
    if not path.exists():complete=False;continue
    native=json.loads(path.read_text());records=native['records'];values=[];checks=[]
    if len(records)!=10:complete=False;continue
    for case,record in zip(spec['cases'],records):
        text=record.get('text','') or '';match=re.search(r'\{[\s\S]*\}',text);actual=None
        try:actual=json.loads(match.group(0)) if match else None
        except ValueError:pass
        field_checks={field:bool(isinstance(actual,dict) and actual.get(field)==expected) for field,expected in case['expected'].items()}
        values.extend(int(x) for x in field_checks.values());checks.append({'case_id':case['case_id'],'sha256':case['sha256'],'actual':actual,'field_checks':field_checks})
    frameworks[framework]={'values':values,'passed':sum(values),'total':len(values),'entrypoints':[native['entrypoint']],'evidence':[str(path.relative_to(ROOT))],'case_results':checks}
if complete:
    payload={'row':16,'title':'感知管理','metric':'图像字段提取正确率','unit':'%','direction':'higher','scope':'相同10张合成PNG通过原生模型图片内容链路传入deepseek-flash，提取编号、蓝色圆形数量和金额，共30个字段。OpenClaw原生provider适配器、Hermes原生Agent多模态输入。','limitations':['仅测静态图像三类字段，不代表语音、视频、设备节点或复杂环境融合。','共同模型会主导视觉准确率；不把本结果解释为框架自有视觉模型性能。','OpenClaw为原生provider图片请求链路，未覆盖所有Gateway附件预处理入口。'],'status':'measured','frameworks':frameworks,'model':'deepseek-flash','source':'https://api-docs.deepseek.com/guides/vision/'}
    (ROOT/'results/extended-row-16.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
    print(json.dumps({'row':16,'results':{f:[x['passed'],x['total']] for f,x in frameworks.items()}}))
