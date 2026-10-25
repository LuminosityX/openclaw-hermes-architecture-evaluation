"""Real subprocess workload shared by both framework tool executors."""
import argparse
import fcntl
import json
import os
import re
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--run-id", required=True)
parser.add_argument("--id", type=int, required=True)
parser.add_argument("--delay-ms", type=int, default=200)
args = parser.parse_args()
if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_id):
    raise SystemExit("Invalid run id")
path = Path(__file__).resolve().parents[1] / "raw" / "tool-events.jsonl"
def emit(kind):
    with path.open("a") as output:
        fcntl.flock(output, fcntl.LOCK_EX)
        output.write(json.dumps({"run_id": args.run_id, "id": args.id, "event": kind, "timestamp_ns": time.monotonic_ns(), "pid": os.getpid()}) + "\n")
        output.flush()
        fcntl.flock(output, fcntl.LOCK_UN)
emit("start")
time.sleep(args.delay_ms / 1000)
emit("end")
print(json.dumps({"id": args.id, "status": "ok", "run_id": args.run_id}))
