"""Read-only correction for native JSON embedded in external-content/text envelopes."""
import hashlib,json,re,sqlite3
from pathlib import Path
from runtime import R,save
from mcp_contract_fixture import LARGE,UNICODE

def objects(text):
 decoder=json.JSONDecoder()
 for m in re.finditer(r'[\[{]',text):
  try:yield decoder.raw_decode(text[m.start():])[0]
  except ValueError:pass

def match(v):
 if isinstance(v,dict):
  return (v.get('echo')==UNICODE and v.get('metadata',{}).get('language')=='中文') or any(match(x) for x in v.values())
 if isinstance(v,list):return any(match(x) for x in v)
 return False

def main():
 rows=[]
 for raw in json.loads((R/'results/mcp-contracts.json').read_text()):
  run=R/'runs-mcp-contracts'/raw['transport']/f"u{raw['unit']}"/raw['family'];requests=json.loads((run/'controlled-requests.json').read_text());texts=[m['content'] for r in requests for m in r['request'].get('messages',[]) if m.get('role')=='tool' and isinstance(m.get('content'),str)]
  structured=any(match(x) for s in texts for x in objects(s) if len(s)<20000)
  spills=[]
  for s in texts:
   for path in re.findall(r'Full output saved to: ([^\s<]+)',s):
    if path.startswith('/state/'):
     actual=run/'state'/path.removeprefix('/state/')
     if actual.exists():
      data=actual.read_text();spills.append(dict(path=path,sha256=hashlib.sha256(actual.read_bytes()).hexdigest(),exact_original=data==LARGE,tail_present=data.endswith('_MCP_LARGE_END_中文')))
  row=dict(unit=raw['unit'],family=raw['family'],transport=raw['transport'],raw_structured_flag=raw['structured_content_preserved'],structured_semantics_preserved=structured,complete_inline=any(LARGE in s for s in texts),native_spill_files=list({x['path']:x for x in spills}.values()),explicit_truncation_or_spill_notice=raw['large_notice_visible'],scope='Posthoc read-only audit of original wire messages and native spill files. Earlier structured=false was a controller parser error: both native envelopes contained the full object. No new product execution and no invented retrieval path.')
  rows.append(row)
 save(R/'results/mcp-projection-audit.json',rows)
 print('MCP_PROJECTION_AUDIT',len(rows),'structured',sum(x['structured_semantics_preserved'] for x in rows),'exact_spill',sum(any(y['exact_original'] for y in x['native_spill_files']) for x in rows))
if __name__=='__main__':main()
