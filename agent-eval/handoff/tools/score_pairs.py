#!/usr/bin/env python3
"""Compute only from complete, evidenced pair decisions. No model judgments."""
import argparse,csv,itertools,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FAMILIES=['openclaw','hermes','codex','dsh']

def score(path):
    with Path(path).open(newline='') as f:rows=list(csv.DictReader(f))
    expected={(f'D{i:02d}',a,b) for i in range(1,12) for a,b in itertools.combinations(FAMILIES,2)}
    keys=[(r['dimension_id'],r['family_a'],r['family_b']) for r in rows]
    if len(keys)!=66 or set(keys)!=expected:raise ValueError('Expected exactly the 66 canonical pairs, with no duplicates')
    out=[]
    for dim in [f'D{i:02d}' for i in range(1,12)]:
        for fam in FAMILIES:
            points=0;missing=[]
            for r in rows:
                if r['dimension_id']!=dim or fam not in [r['family_a'],r['family_b']]:continue
                decision=r['decision']
                if decision not in ['A优','B优','相当'] or not r.get('evidence','').strip() or not r.get('reviewer','').strip():
                    missing.append(r['family_b'] if fam==r['family_a'] else r['family_a']);continue
                if decision=='相当':points+=0.5
                elif (decision=='A优' and fam==r['family_a']) or (decision=='B优' and fam==r['family_b']):points+=1
            out.append({'dimension_id':dim,'family':fam,'points':None if missing else points,
                        'grade':None if missing else '强' if points>=2.5 else '弱' if points<=0.5 else '中',
                        'status':'insufficient_evidence' if missing else 'computed_from_reviewed_pairs','missing_comparisons':missing})
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pairs',default=str(ROOT/'records/pairwise.csv'));a=p.parse_args()
    print(json.dumps(score(a.pairs),ensure_ascii=False,indent=2))
