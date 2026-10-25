"""Check the exact-rational oracle against original generator truth and an independent Decimal implementation."""
import csv,json,shutil,subprocess
from pathlib import Path
from runtime import R,save
from reuse_data_oracle import expected
REFERENCE=Path('/root/output/oc-hermes-comparison-20261024-v5/evidence/data-checker-selftest/workspace/reconcile_data.py')
def main():
 records=[]
 for variant in range(1,4):
  source=R/'fixtures'/f'W3-v{variant}'/'sources';original=json.loads((R/'private'/f'W3-v{variant}-expected.json').read_text());up=expected(source,False);case=R/'evidence/reuse-oracle-selftest'/f'v{variant}';case.mkdir(parents=True,exist_ok=True);script=case/'decimal-even-reference.py';script.write_text(REFERENCE.read_text().replace('ROUND_HALF_UP','ROUND_HALF_EVEN'));out=case/'output';subprocess.run(['/usr/bin/python3',str(script),'--input-dir',str(source),'--output-dir',str(out)],check=True,capture_output=True)
  with(out/'summary.csv').open(newline='') as f:rows=list(csv.DictReader(f))
  even=expected(source,True);match=even==dict(summary=rows,audit=json.loads((out/'audit.json').read_text()));rec=dict(variant=variant,half_up_matches_frozen_generator_truth=up==original,half_even_matches_independent_decimal_program=match,rule_change_material=up['summary']!=even['summary']);records.append(rec)
 save(R/'evidence/reuse-oracle-selftest/result.json',dict(passed=all(all(r[k] for k in ['half_up_matches_frozen_generator_truth','half_even_matches_independent_decimal_program','rule_change_material']) for r in records),checks=records,model_calls=0))
 if not all(r['half_up_matches_frozen_generator_truth'] and r['half_even_matches_independent_decimal_program'] and r['rule_change_material'] for r in records):raise RuntimeError('Data oracle/rule-change contract mismatch before model exposure')
 print('INDEPENDENT_REUSE_ORACLES_VERIFIED',len(records),flush=True)
if __name__=='__main__':main()
