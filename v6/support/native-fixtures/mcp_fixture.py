"""Concurrent stdio MCP fixture with a deterministic, read-only delay tool."""
import fcntl
import json
import os
from pathlib import Path
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
WRITE = threading.Lock()

def event(run_id, index, kind):
    with (ROOT / "raw/tool-events.jsonl").open("a") as output:
        fcntl.flock(output, fcntl.LOCK_EX)
        output.write(json.dumps({"run_id": run_id, "id": index, "event": kind, "timestamp_ns": time.monotonic_ns(), "pid": os.getpid(), "origin": "mcp"}) + "\n")
        output.flush()
        fcntl.flock(output, fcntl.LOCK_UN)

def respond(request):
    if "id" not in request:
        return
    method = request.get("method")
    params = request.get("params", {})
    if method == "initialize":
        result = {"protocolVersion": params.get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "benchmark-readonly-delay", "version": "1.0.0"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [{"name": "bench_delay", "description": "Independent read-only deterministic wait used to measure tool scheduling.", "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}, "id": {"type": "integer"}, "delay_ms": {"type": "integer", "minimum": 0, "maximum": 10000}}, "required": ["run_id", "id", "delay_ms"], "additionalProperties": False}, "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}}]}
    elif method == "tools/call" and params.get("name") == "bench_delay":
        args = params.get("arguments", {})
        run_id = str(args["run_id"])
        index = int(args["id"])
        delay = max(0, min(int(args["delay_ms"]), 10000))
        event(run_id, index, "start")
        time.sleep(delay / 1000)
        event(run_id, index, "end")
        result = {"content": [{"type": "text", "text": json.dumps({"run_id": run_id, "id": index, "status": "ok", "delay_ms": delay})}], "isError": False}
    else:
        with WRITE:
            print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32601, "message": "Method not found"}}), flush=True)
        return
    with WRITE:
        print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)

with ThreadPoolExecutor(max_workers=16) as pool:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            pool.submit(respond, request)
        except json.JSONDecodeError:
            continue
