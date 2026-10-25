import os,sys,json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=R/'fixtures/extended-context/hermes-profile';D.mkdir(parents=True,exist_ok=True)
os.environ['HERMES_HOME']=str(D);os.environ['HERMES_RUNTIME_DIR']=str(D/'runtime')
(D/'config.yaml').write_text('terminal:\n  backend: local\n')
sys.path.insert(0,str(R/'sources/hermes'))
from tools.budget_config import budget_for_context_window
from tools.tool_result_storage import maybe_persist_tool_result,extract_persisted_path,enforce_turn_budget
sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
cases=[]
for c in json.loads((R/'fixtures/extended-context/manifest.json').read_text()):
 text=Path(c['path']).read_text();config=budget_for_context_window(c['context'])
 result=maybe_persist_tool_result(text,'bench_data',c['name'],config=config)
 projected=enforce_turn_budget([dict(role='tool',tool_call_id=c['name'],content=result)],config=config)
 inline=projected[0]['content'];archive=extract_persisted_path(inline)
 archive_sha=sha(Path(archive).read_text()) if archive and Path(archive).is_file() else None
 integrity=archive_sha==c['sha256'] if archive else sha(inline)==c['sha256']
 truncated=inline!=text;notice=('<persisted-output>' in inline or 'Truncated:' in inline) if truncated else True
 budget=config.resolve_threshold('bench_data');within=len(inline)<=budget
 evidence_file=R/'raw/extended-controls'/f'context-hermes-{c["name"]}.txt';evidence_file.write_text(inline)
 cases.append({**c,'actual':dict(budget_chars=budget,turn_budget_chars=config.turn_budget,inline_codepoints=len(inline),inline_utf8_bytes=len(inline.encode()),inline_fraction_utf8=len(inline.encode())/c['utf8_bytes'],truncated=truncated,notice=notice,archive_path=archive,archive_sha256=archive_sha,recoverable_content_integrity=integrity,markers_inline={k:v in inline for k,v in c['markers'].items()},markers_archive={k:v in Path(archive).read_text() for k,v in c['markers'].items()} if archive else None),'expected':dict(within_native_budget=True,truncation_notice_when_needed=True,recoverable_content_integrity=True),'passed':bool(within and notice and integrity),'evidence_file':str(evidence_file.relative_to(R))})
(R/'raw/extended-controls/context-hermes.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
print(json.dumps(dict(passed=sum(x['passed'] for x in cases),total=len(cases),inline_fractions=[(x['name'],x['actual']['inline_fraction_utf8']) for x in cases])))
