#!/usr/bin/env python3
"""Real native Hermes agent run; private credentials never enter result artifacts."""
import argparse
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from configure_deepseek import configured_key, BASE_URL, MODEL

ROOT = Path(__file__).resolve().parents[1]
USAGE_KEYS = ["api_calls", "input_tokens", "output_tokens", "prompt_tokens", "completion_tokens",
    "total_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens", "estimated_cost_usd", "cost_status", "cost_source"]


def protect_diagnostics(key):
    factory = logging.getLogRecordFactory()

    def redacted_factory(*args, **kwargs):
        record = factory(*args, **kwargs)
        record.msg, record.args = record.getMessage().replace(key, "[REDACTED]"), ()
        if record.exc_info:
            record.exc_text = "".join(traceback.format_exception(*record.exc_info)).replace(key, "[REDACTED]")
            record.exc_info = None
        return record

    logging.setLogRecordFactory(redacted_factory)
    class RedactedStream:
        def __init__(self, stream):
            self.stream = stream

        def write(self, value):
            return self.stream.write(value.replace(key, "[REDACTED]"))

        def __getattr__(self, name):
            return getattr(self.stream, name)

    sys.stdout, sys.stderr = RedactedStream(sys.stdout), RedactedStream(sys.stderr)


def main():
    p = argparse.ArgumentParser()
    text = p.add_mutually_exclusive_group(required=True)
    text.add_argument("--prompt")
    text.add_argument("--prompt-file", type=Path)
    p.add_argument("--run-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--max-iterations", type=int, default=6)
    p.add_argument("--max-tokens", type=int, default=4096)
    p.add_argument("--cwd", type=Path, default=ROOT / "fixtures/real-model-workspace")
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    key = configured_key()
    if not key:
        args.output.write_text(json.dumps({"framework": "hermes", "run_id": args.run_id,
            "status": "needs_private_key", "base_url": BASE_URL, "model": MODEL, "api_calls": 0}, indent=2))
        print(json.dumps({"status": "needs_private_key", "output": str(args.output), "api_calls": 0}))
        return 2
    protect_diagnostics(key)
    prompt = args.prompt if args.prompt is not None else args.prompt_file.read_text()
    profile = ROOT / "runtime/hermes-real-cases" / args.run_id
    profile.mkdir(parents=True, exist_ok=True)
    args.cwd.mkdir(parents=True, exist_ok=True)
    (profile / "config.yaml").write_text(json.dumps({"model": {"context_length": 128000},
        "terminal": {"backend": "local", "cwd": str(args.cwd.resolve())},
        "tools": {"tool_search": {"enabled": "off"}}, "background_review": {"enabled": False}}))
    os.environ["HERMES_HOME"] = str(profile)
    os.environ["HERMES_RUNTIME_DIR"] = str(profile / "runtime")
    os.chdir(args.cwd)
    sys.path.insert(0, str(ROOT / "sources/hermes"))
    payload = {"framework": "hermes", "run_id": args.run_id, "base_url": BASE_URL, "model": MODEL,
        "scope": "Real-model native AIAgent run with local terminal tools; task correctness must be evaluated independently.",
        "correct": None, "thinking": {"type": "disabled"}, "temperature": 0, "max_tokens": args.max_tokens,
        "max_iterations": args.max_iterations, "context_length": 128000, "prompt": prompt,
        "commit": subprocess.check_output(["git", "-C", str(ROOT / "sources/hermes"), "rev-parse", "HEAD"], text=True).strip()}
    agent = None
    started = time.perf_counter_ns()
    try:
        from run_agent import AIAgent
        agent = AIAgent(api_key=key, base_url=BASE_URL, provider="custom", api_mode="chat_completions", model=MODEL,
            enabled_toolsets=["terminal", "file"], quiet_mode=True, skip_context_files=True,
            skip_memory=True, skip_background_review=True, max_iterations=args.max_iterations,
            max_tokens=args.max_tokens, cwd=str(args.cwd.resolve()), reasoning_config={"enabled": False},
            request_overrides={"temperature": 0, "extra_body": {"thinking": {"type": "disabled"}}})
        init_end = time.perf_counter_ns()
        result = agent.run_conversation(prompt)
        end = time.perf_counter_ns()
        payload.update({"status": "completed" if result.get("completed") and not result.get("failed") else "incomplete",
            "initialize_ms": (init_end-started)/1e6, "conversation_ms": (end-init_end)/1e6,
            "usage": {k: result.get(k) for k in USAGE_KEYS}, "final_response": result.get("final_response"),
            "messages": result.get("messages"), "turn_exit_reason": result.get("turn_exit_reason"),
            "completed": result.get("completed"), "failed": result.get("failed"), "interrupted": result.get("interrupted")})
    except Exception as exc:
        payload.update({"status": "error", "error_type": type(exc).__name__, "http_status": getattr(exc, "status_code", None),
            "elapsed_ms": (time.perf_counter_ns()-started)/1e6})
        if agent is not None:
            payload["usage"] = {k: getattr(agent, "session_" + k, None) for k in USAGE_KEYS}
    finally:
        if agent is not None:
            try:
                agent.close()
            except Exception as exc:
                payload["cleanup_error_type"] = type(exc).__name__
    # Preserve only task evidence and accounting. Never serialize the client or request headers.
    args.output.write_text(json.dumps(payload, indent=2, default=str).replace(key, "[REDACTED]"))
    print(json.dumps({"status": payload["status"], "output": str(args.output)}))
    return 0 if payload["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
