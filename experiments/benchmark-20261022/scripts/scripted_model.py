"""Local protocol fixture: deterministic tool plans, no real model or API spending.

Measures framework execution only. Its synthetic token usage is never a cost metric.
"""
import argparse
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = threading.Lock()

def content_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(x.get("text", "") for x in value if isinstance(x, dict))
    return ""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_json({"object": "list", "data": [{"id": "bench-scripted", "object": "model", "owned_by": "local-fixture"}]})

    def send_json(self, value, status=200):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            messages = body.get("messages", [])
            user_text = "\n".join(content_text(m.get("content")) for m in messages if m.get("role") == "user")
            run = re.search(r"BENCH_RUN_ID=([A-Za-z0-9_-]+)", user_text)
            count_match = re.search(r"BENCH_TOOL_COUNT=(\d+)", user_text)
            batches_match = re.search(r"BENCH_BATCHES=(\d+)", user_text)
            delay_match = re.search(r"BENCH_DELAY_MS=(\d+)", user_text)
            run_id = run.group(1) if run else "smoke"
            count = min(int(count_match.group(1)), 16) if count_match else 0
            batches = min(int(batches_match.group(1)), 100) if batches_match else 1
            expected_total = count * batches
            delay = min(int(delay_match.group(1)), 30000) if delay_match else 200
            tool_results = [m for m in messages if m.get("role") == "tool"]
            names = [t.get("function", {}).get("name", "") for t in body.get("tools", [])]
            mcp_case = "BENCH_TOOL_KIND=mcp" in user_text
            serial = "BENCH_MODE=serial" in user_text
            tool_name = next((n for n in names if "bench_delay" in n), None) if mcp_case else next((n for n in names if n in ["exec", "terminal"]), None)
            if tool_name is None:
                tool_name = next((n for n in names if n.endswith("_exec") or n.endswith("_terminal")), None)
            calls = []
            should_call = count and tool_name and len(tool_results) < expected_total
            if should_call:
                indices = [len(tool_results)] if serial else range(len(tool_results), min(len(tool_results)+count, expected_total))
                for i in indices:
                    command = f"/usr/bin/python3 {ROOT / 'scripts/delay_tool.py'} --run-id {run_id} --id {i} --delay-ms {delay}"
                    arguments = {"run_id": run_id, "id": i, "delay_ms": delay} if mcp_case else {"command": command}
                    if tool_name == "terminal" and not mcp_case:
                        arguments["background"] = False
                    calls.append({"id": f"call_{run_id}_{i}", "type": "function", "function": {"name": tool_name, "arguments": json.dumps(arguments)}})
            final = json.dumps({"fixture": "scripted-model-v1", "run_id": run_id, "observed_tool_results": len(tool_results), "expected_tool_results": expected_total, "tool_available": tool_name is not None})
            message = {"role": "assistant", "content": None if calls else final}
            if calls:
                message["tool_calls"] = calls
            reason = "tool_calls" if calls else "stop"
            event = {"timestamp_ns": time.monotonic_ns(), "run_id": run_id, "path": self.path, "stream": bool(body.get("stream")), "model": body.get("model"), "tool_names": names, "selected_tool": tool_name, "returned_calls": len(calls), "observed_tool_results": len(tool_results), "expected_total": expected_total}
            with LOCK, (ROOT / "raw/model-requests.jsonl").open("a") as output:
                output.write(json.dumps(event) + "\n")
            identifier = f"chatcmpl-{run_id}"
            created = int(time.time())
            if not body.get("stream"):
                self.send_json({"id": identifier, "object": "chat.completion", "created": created, "model": "bench-scripted", "choices": [{"index": 0, "message": message, "finish_reason": reason}], "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            delta = {"role": "assistant"}
            if calls:
                delta["tool_calls"] = [{"index": i, **call} for i, call in enumerate(calls)]
            else:
                delta["content"] = final
            for d, finish in [(delta, None), ({}, reason)]:
                chunk = {"id": identifier, "object": "chat.completion.chunk", "created": created, "model": "bench-scripted", "choices": [{"index": 0, "delta": d, "finish_reason": finish}]}
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as error:
            self.send_json({"error": {"message": str(error), "type": "fixture_error"}}, 500)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    options = parser.parse_args()
    (ROOT / "raw").mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", options.port), Handler)
    actual_port = server.server_address[1]
    (ROOT / "results/model-fixture.json").write_text(json.dumps({"port": actual_port, "base_url": f"http://127.0.0.1:{actual_port}/v1", "model": "bench-scripted", "real_model": False}, indent=2))
    print(json.dumps({"status": "listening", "port": actual_port}), flush=True)
    server.serve_forever()
