import json,statistics
from pathlib import Path
R=Path(__file__).resolve().parents[1]
raw={fw:json.loads((R/f'raw/extended-controls/context-{fw}.json').read_text()) for fw in ['openclaw','hermes']}
entrypoints={
'openclaw':['src/agents/embedded-agent-runner/tool-result-truncation.ts:truncateOversizedToolResultsInMessages','src/agents/tool-result-limits.ts:resolveLiveToolResultMaxChars'],
'hermes':['tools/budget_config.py:budget_for_context_window','tools/tool_result_storage.py:maybe_persist_tool_result','tools/tool_result_storage.py:enforce_turn_budget'],
}
frameworks={}
for fw,cases in raw.items():
 values=[int(c['passed']) for c in cases]
 frameworks[fw]=dict(values=values,passed=sum(values),total=len(values),entrypoints=entrypoints[fw],evidence=[f'raw/extended-controls/context-{fw}.json']+[c['evidence_file'] for c in cases])
out=dict(row=5,title='上下文管理',metric='长工具输出预算与保留契约通过率',unit='%',direction='higher',status='measured',
scope='12组固定长工具输出：32k/128k上下文×20k/100k/500k字符×ASCII/中英emoji。执行原生裁剪/存储函数，检查内联结果不超各自原生预算、缩减时存在提示、原始输出在原消息或原生spill档案中保持SHA-256完整。',
limitations=[
'这是长工具输出保护组件实验，未测真实模型回答、压缩摘要质量、长期事实问答或实际API Token。',
'OpenClaw在此路径保留原toolResult消息并投影裁剪；没有自动返回spill档案路径。Hermes超阈值写spill档案并返回读取路径。原消息保留不等于模型能自动读取全文，未将这两种机制当作同等检索能力。',
'两边默认预算不同，OpenClaw按加权字符计量预算、Hermes按Python字符数计量预算，内联比例只描述默认策略，不以越小越好排名。',
'档案SHA只核验原生返回的文件路径，未给OpenClaw补造spill文件；非ASCII输入使用相同UTF-8文件。',
],frameworks=frameworks,
secondary_metrics={
'inline_utf8_fraction':dict(metric='原生处理后内联UTF-8字节占原输出比例',unit='%',direction='descriptive',case_labels=[c['name'] for c in raw['openclaw']],frameworks={fw:[round(c['actual']['inline_fraction_utf8']*100,4) for c in cases] for fw,cases in raw.items()}),
'original_message_or_archive_integrity':dict(metric='原消息或返回归档内容SHA-256完整率',unit='%',direction='higher',frameworks={fw:[int(c['actual'].get('original_message_preserved',c['actual'].get('recoverable_content_integrity',False))) for c in cases] for fw,cases in raw.items()}),
'model_visible_archive_reference':dict(metric='返回可读归档路径的用例数',unit='count',direction='descriptive',frameworks={fw:sum(bool(c['actual']['archive_path']) for c in cases) for fw,cases in raw.items()}),
'inline_marker_retention':dict(metric='首中尾标记内联保留数量',unit='count',direction='descriptive',frameworks={fw:[sum(c['actual']['markers_inline'].values()) for c in cases] for fw,cases in raw.items()}),
})
(R/'results/extended-row-05.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({fw:{'passed':v['passed'],'total':v['total'],'returned_archive_count':out['secondary_metrics']['model_visible_archive_reference']['frameworks'][fw]} for fw,v in frameworks.items()},ensure_ascii=False))
