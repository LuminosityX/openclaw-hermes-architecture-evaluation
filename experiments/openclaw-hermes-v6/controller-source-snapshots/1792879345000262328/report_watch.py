"""Refresh reviewable evidence tables when a formal result is written; zero model/product runs."""
import json,time,os
from pathlib import Path
from runtime import R,save
import summarize,analyze_calls,reconcile_usage
save(R/'evidence/report-watch-pid.json',dict(pid=os.getpid(),started=time.time()))
previous=None
while not (R/'evidence/stop-report-watch').exists():
 signature=tuple((str(p),p.stat().st_mtime_ns) for p in sorted((R/'runs/formal').glob('*/*/result.json')))
 if signature!=previous:
  reconcile_usage.main();summarize.main();analyze_calls.main();previous=signature
 time.sleep(2)
