#!/usr/bin/env python3
"""One real native Hermes conversation containing successive scripted MCP batches."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from hermes_agent_case import parse_tool_payload

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://127.0.0.1:38691/v1")
    p.add_argument("--batches", type=int, default=35)
    p.add_argument("--count", type=int, default=4)
    p.add_argument("--warmups", type=int, default=5)
    p.add_argument("--delay-ms", type=int, default=200)
    p.add_argument("--run-id", default="hermes-mcp-batches")
    p.add_argument("--output", type=Path, default=ROOT / "raw/hermes-mcp-batches.json")
    args = p.parse_args()
    if args.batches <= args.warmups or args.count < 1:
        p.error("batches must exceed warmups and count must be positive")
    profile = ROOT / "runtime/hermes-mcp-batches" / args.run_id
    profile.mkdir(parents=True, exist_ok=True)
    (profile / "config.yaml").write_text(json.dumps({"model": {"context_length": 128000},
        "tools": {"tool_search": {"enabled": "off"}}, "background_review": {"enabled": False},
        "timeouts": {"tools": {"concurrent_batch": 120}},
        "mcp_servers": {"bench": {"command": "/usr/bin/python3", "args": [str(ROOT / "scripts/mcp_fixture.py")],
            "supports_parallel_tool_calls": True, "trust": "full", "lazy": False}}}))
    os.environ["HERMES_HOME"] = str(profile)
    os.environ["HERMES_RUNTIME_DIR"] = str(profile / "runtime")
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "sources/hermes"))
    from run_agent import AIAgent
    from tools.mcp_tool_discovery import discover_mcp_tools, is_mcp_tool_parallel_safe
    from tools.mcp_tool_lifecycle import shutdown_mcp_servers
    agent = None
    expected = args.batches * args.count
    prompt = f"BENCH_RUN_ID={args.run_id} BENCH_TOOL_KIND=mcp BENCH_TOOL_COUNT={args.count} BENCH_BATCHES={args.batches} BENCH_DELAY_MS={args.delay_ms}"
    payload = {"framework": "hermes", "row": 8, "run_id": args.run_id, "batches": args.batches,
        "count_per_batch": args.count, "warmup_batches": args.warmups, "measured_batches": args.batches-args.warmups,
        "delay_ms": args.delay_ms, "expected_tool_results": expected, "prompt": prompt,
        "scope": "One native AIAgent conversation, one MCP stdio connection, successive scripted model batches. Warmups and samples are within-session batches; startup and API latency are excluded from independently reconstructed tool execution spans.",
        "commit": subprocess.check_output(["git", "-C", str(ROOT / "sources/hermes"), "rev-parse", "HEAD"], text=True).strip()}
    try:
        discovery_start = time.perf_counter_ns()
        discovered = discover_mcp_tools(["bench"])
        payload["mcp_discovery_ms"] = (time.perf_counter_ns()-discovery_start)/1e6
        payload["discovered_tools"] = discovered
        if not any(name.endswith("bench_delay") and is_mcp_tool_parallel_safe(name) for name in discovered):
            raise RuntimeError("Native MCP parallel-safety admission failed")
        agent = AIAgent(api_key="bench-local", base_url=args.base_url, provider="custom", api_mode="chat_completions",
            model="bench-scripted", enabled_toolsets=["bench"], quiet_mode=True, skip_context_files=True,
            skip_memory=True, skip_background_review=True, max_iterations=max(40, args.batches+5),
            run_budget_seconds=max(600, args.batches*args.count*args.delay_ms/1000+120), cwd=str(ROOT))
        started = time.perf_counter_ns()
        result = agent.run_conversation(prompt)
        ended = time.perf_counter_ns()
        tool_results, parse_errors = [], []
        for message in result.get("messages", []):
            if message.get("role") != "tool":
                continue
            try:
                outer = parse_tool_payload(message["content"])
                value = outer.get("result", {})
                tool_results.append(json.loads(value) if isinstance(value, str) else value)
            except (TypeError, ValueError, KeyError) as exc:
                parse_errors.append({"tool_call_id": message.get("tool_call_id"), "error": str(exc)})
        final = json.loads(result.get("final_response") or "{}")
        ids = [x.get("id") for x in tool_results]
        correct = (not parse_errors and len(tool_results) == expected and set(ids) == set(range(expected))
            and all(x.get("run_id") == args.run_id and x.get("status") == "ok" for x in tool_results)
            and final.get("observed_tool_results") == expected and final.get("expected_tool_results") == expected
            and result.get("api_calls") == args.batches+1)
        payload.update({"correct": correct, "conversation_ms": (ended-started)/1e6,
            "api_calls": result.get("api_calls"), "completed": result.get("completed"), "failed": result.get("failed"),
            "turn_exit_reason": result.get("turn_exit_reason"), "final_response": result.get("final_response"),
            "messages": result.get("messages"), "parsed_tool_results": tool_results, "parse_errors": parse_errors})
    except Exception as exc:
        payload.update({"correct": False, "error_type": type(exc).__name__, "error": str(exc)})
    finally:
        if agent is not None:
            agent.close()
        shutdown_mcp_servers(names={"bench"}, timeout=5)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, default=str))
    print(json.dumps({"output": str(args.output), "correct": payload["correct"], "api_calls": payload.get("api_calls"), "tool_results": len(payload.get("parsed_tool_results", [])), "error_type": payload.get("error_type")}))
    return 0 if payload["correct"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
