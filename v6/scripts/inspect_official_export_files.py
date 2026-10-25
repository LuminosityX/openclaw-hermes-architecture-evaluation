"""Candidate evidence from vendor-produced local exports. No operator files admitted.
Identifier presence alone is never an assertion that an approval outcome is auditable.
"""
import hashlib,json
from pathlib import Path

def candidates(state,family,identities):
 state=Path(state);vendor=state/('hermes' if family=='hermes' else 'openclaw');roots=[vendor/'logs',vendor/'telemetry'];rows=[]
 for root in roots:
  if not root.exists():continue
  for p in sorted(root.rglob('*')):
   if not p.is_file() or p.suffix not in ['.json','.jsonl','.log','.ndjson']:continue
   data=p.read_bytes();text=data.decode(errors='replace');hits=[]
   for i,line in enumerate(text.splitlines(),1):
    found=[key for key in identities if key in line]
    if found:
     try:record=json.loads(line)
     except ValueError:record=line
     hits.append(dict(line=i,matching_ids=found,record=record))
   rows.append(dict(source=str(p.relative_to(state)),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),matching_ids=[key for key in identities if key in text],matching_lines=hits,scope='Native vendor log/telemetry file. Matches are evidence candidates for semantic review, not proof of a decision merely because a UUID occurs in request text.'))
 return rows
