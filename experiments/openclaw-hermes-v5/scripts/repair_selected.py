import json,os
from pathlib import Path
R=Path(__file__).resolve().parents[1]
from run_mechanisms import run_one,OLD,save
os.chdir(OLD)
archive=R/'evidence/mechanisms-invalid-config';archive.mkdir(exist_ok=True)
for kind,family in [('deny','openclaw'),('plugin-host','openclaw'),('plugin-host','hermes'),('plugin-in-process','hermes')]:
 old=R/'runs-mechanisms'/kind/family
 if old.exists():
  target=archive/(kind+'-'+family)
  if target.exists():raise RuntimeError('Archive target already exists')
  old.rename(target)
 result=run_one(family,kind)
 print('REPAIRED_RESULT',kind,family,json.dumps(result,ensure_ascii=False),flush=True)
for family in ['openclaw','hermes']:
 old=R/'runs-mechanisms/http-scale'/family
 if old.exists():old.rename(archive/('http-scale-'+family))
import run_scale
run_scale.main()
