#!/usr/bin/env python3
"""Integrity check of immutable handoff files; not an authenticity signature."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
errors=[];count=0
for line in (ROOT/'MANIFEST.sha256').read_text().splitlines():
    expected,name=line.split('  ',1);p=ROOT/name;count+=1
    if not p.is_file():errors.append({'path':name,'error':'missing'})
    elif hashlib.sha256(p.read_bytes()).hexdigest()!=expected:errors.append({'path':name,'error':'hash_mismatch'})
print(json.dumps({'checked':count,'passed':not errors,'errors':errors,'scope':'immutable package inputs only; records/state/runs are mutable'},ensure_ascii=False,indent=2))
raise SystemExit(1 if errors else 0)
