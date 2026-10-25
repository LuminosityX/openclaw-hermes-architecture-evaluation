#!/usr/bin/env python3
"""Prepare isolated public input and an empty record. Does not run an agent."""
import argparse, json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ["openclaw", "hermes", "codex", "dsh"]

def prepare(family, task, variant, repeat, phase, runs_root=None):
    target = (Path(runs_root) if runs_root else ROOT / "runs") / phase / family / task / variant / f"r{repeat}"
    if target.exists():
        raise FileExistsError(f"Existing run preserved: {target}")
    source = ROOT / "tasks" / task / variant
    if not source.is_dir(): raise ValueError("Unknown task/variant")
    target.mkdir(parents=True)
    shutil.copytree(source, target / "workspace")
    run_id=f"{phase}-{family}-{task}-{variant}-r{repeat}"
    (target/'workspace/RUN_ID.txt').write_text(run_id+'\n')
    cfg = json.loads((ROOT / "experiment.json").read_text())
    record = json.loads((ROOT / "records/run_record.template.json").read_text())
    record.update({"run_id": run_id, "family": family,
                   "task": task, "variant": variant, "repeat": repeat, "phase": phase,
                   "required_model": cfg["families"][family]["model"], "status": "prepared_not_started",
                   "workspace": str(target / "workspace")})
    (target / "run_record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
    return target

if __name__ == "__main__":
    p=argparse.ArgumentParser();p.add_argument("--family",choices=FAMILIES,required=True)
    p.add_argument("--task",choices=[f"W{i}" for i in range(1,7)],required=True)
    p.add_argument("--variant",choices=["v1","v2","v3"],required=True)
    p.add_argument("--repeat",type=int,default=1);p.add_argument("--phase",choices=["pilot","formal","selfcheck"],default="pilot")
    a=p.parse_args()
    if a.repeat<1:p.error("repeat must be positive")
    print(prepare(a.family,a.task,a.variant,a.repeat,a.phase))
