#!/usr/bin/env python3
"""Coordinator-side functional checks; this is not a sandbox for candidate code."""
import argparse, csv, importlib.util, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def evaluate(run):
    run=Path(run).resolve(); rec=json.loads((run/"run_record.json").read_text())
    task,variant=rec["task"],rec["variant"]; work=run/"workspace"
    private=ROOT/"evaluator_private"/task/variant
    result={"task":task,"variant":variant,"kind":"functional_check_only","passed":False}
    if task in ("W1","W2"):
        cmd=[sys.executable,str(private/"check.py"),str(work)]
        try:
            c=subprocess.run(cmd,cwd=work,capture_output=True,text=True,timeout=25)
            result.update(passed=c.returncode==0,returncode=c.returncode,stdout=c.stdout[-16000:],stderr=c.stderr[-16000:])
        except subprocess.TimeoutExpired:
            result.update(error="evaluator_timeout",passed=False)
    elif task=="W3":
        expected=json.loads((private/"expected.json").read_text());errors=[]
        try:
            actual=json.loads((work/"output/summary.json").read_text())
            if actual!=expected["summary"]:errors.append("summary.json differs from golden result")
            with (work/"output/clean.csv").open(newline="") as f:
                reader=csv.DictReader(f);rows=list(reader)
                if reader.fieldnames!=expected["columns"]:errors.append("clean.csv columns differ")
            if rows!=expected["clean"]:errors.append("clean.csv rows differ")
        except Exception as e:errors.append(f"{type(e).__name__}: {e}")
        result.update(passed=not errors,errors=errors)
    elif task=="W4":
        path=work/"report.md"; expected=json.loads((private/"rubric.json").read_text());issues=[]
        if not path.exists():issues.append("report.md missing")
        else:
            text=path.read_text()
            for label in expected["required_sections"]:
                if label not in text:issues.append(f"section missing: {label}")
            for doc in expected["required_citations"]:
                if f"[{doc}]" not in text:issues.append(f"citation missing: {doc}")
        result.update(passed=None,structure_passed=not issues,issues=issues,manual_review_required=True,
                      note="A structurally valid report is not a factual/semantic pass. Review private rubric independently.")
    else:
        result.update(passed=None,manual_review_required=True,note="Use the task's MANUAL_CHECKLIST.md and independent observations; no automatic pass.")
    stamp=time.time_ns();out=run/f"evaluation-{stamp}.json"
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result,out

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--run",required=True);a=p.parse_args()
    r,out=evaluate(a.run);print(json.dumps(r,ensure_ascii=False,indent=2));print("Saved:",out)
    sys.exit(0 if r.get("passed") is True else 2 if r.get("manual_review_required") else 1)
