#!/usr/bin/env python3
"""Fresh native AIAgent sessions with one warmed native MCP connection/process."""
import argparse
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

from hermes_agent_case import parse_tool_payload

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://127.0.0.1:38691/v1")
    p.add_argument("--counts", nargs="+", type=int, default=[4])
    p.add_argument("--modes", nargs="+", choices=["batch", "serial"], default=["batch"])
    p.add_argument("--samples", type=int, default=30)
    p.add_argument("--warmups", type=int, default=5)
    p.add_argument("--delay-ms", type=int, default=200)
    p.add_argument("--seed", type=int, default=20261022)
    p.add_argument("--output", type=Path, default=ROOT / "raw/hermes-mcp-formal.json")
    args = p.parse_args()
    profile = ROOT / "runtime/hermes-mcp-formal" / str(os.getpid())
    profile.mkdir(parents=True, exist_ok=True)
    (profile / "config.yaml").write_text(json.dumps({"model": {"context_length": 128000},
        "tools": {"tool_search": {"enabled": "off"}}, "background_review": {"enabled": False},
        "mcp_servers": {"bench": {"command": "/usr/bin/python3", "args": [str(ROOT / "scripts/mcp_fixture.py")],
            "supports_parallel_tool_calls": True, "trust": "full", "lazy": False}}}))
    os.environ["HERMES_HOME"] = str(profile)
    os.environ["HERMES_RUNTIME_DIR"] = str(profile / "runtime")
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "sources/hermes"))
    from run_agent import AIAgent
    from tools.mcp_tool_discovery import discover_mcp_tools, is_mcp_tool_parallel_safe
    from tools.mcp_tool_lifecycle import shutdown_mcp_servers
    discovered = discover_mcp_tools(["bench"])
    if not any(name.endswith("bench_delay") and is_mcp_tool_parallel_safe(name) for name in discovered):
        shutdown_mcp_servers(names={"bench"}, timeout=5)
        raise RuntimeError("Native MCP discovery/parallel-safety admission failed")
    rng = random.Random(args.seed)
    samples, errors = [], []
    cases = [(count, mode) for count in args.counts for mode in args.modes]

    def once(count, mode, index, warmup):
        run_id = f"hermes-mcp-{os.getpid()}-{count}-{mode}-{'warmup' if warmup else 'sample'}-{index}"
        prompt = f"BENCH_RUN_ID={run_id} BENCH_TOOL_KIND=mcp BENCH_TOOL_COUNT={count} BENCH_DELAY_MS={args.delay_ms} BENCH_MODE={mode}"
        agent = AIAgent(api_key="bench-local", base_url=args.base_url, provider="custom", api_mode="chat_completions",
            model="bench-scripted", enabled_toolsets=["bench"], quiet_mode=True, skip_context_files=True,
            skip_memory=True, skip_background_review=True, max_iterations=max(8, count+4), cwd=str(ROOT))
        start = time.perf_counter_ns()
        try:
            result = agent.run_conversation(prompt)
            end = time.perf_counter_ns()
            records = []
            for message in result.get("messages", []):
                if message.get("role") == "tool":
                    outer = parse_tool_payload(message["content"])
                    value = outer.get("result", {})
                    records.append(json.loads(value) if isinstance(value, str) else value)
            correct = len(records) == count and {x.get("id") for x in records} == set(range(count)) and all(x.get("run_id") == run_id and x.get("status") == "ok" for x in records)
            if not warmup:
                samples.append({"framework": "hermes", "row": 8, "run_id": run_id, "tool_count": count,
                    "mode": mode, "sample": index, "delay_ms": args.delay_ms, "conversation_ms": (end-start)/1e6,
                    "correct": correct, "api_calls": result.get("api_calls"), "messages": result.get("messages"), "final_response": result.get("final_response")})
            if not correct:
                errors.append({"run_id": run_id, "warmup": warmup, "type": "incorrect_tool_results"})
        except Exception as exc:
            errors.append({"run_id": run_id, "warmup": warmup, "type": type(exc).__name__, "error": str(exc)})
        finally:
            agent.close()

    try:
        for count, mode in cases:
            for index in range(args.warmups):
                once(count, mode, index, True)
        order = [(count, mode, index) for count, mode in cases for index in range(args.samples)]
        rng.shuffle(order)
        for count, mode, index in order:
            once(count, mode, index, False)
    finally:
        shutdown_mcp_servers(names={"bench"}, timeout=5)
    payload = {"framework": "hermes", "row": 8,
        "commit": subprocess.check_output(["git", "-C", str(ROOT / "sources/hermes"), "rev-parse", "HEAD"], text=True).strip(),
        "scope": "Real AIAgent native tool scheduling with shared stdio MCP server and scripted local HTTP model. Fresh AIAgent/session for each case in one Python process; MCP connection retained. Imports, discovery, agent initialization and cleanup excluded from conversation_ms. Tool execution spans are independently available by run_id in raw/tool-events.jsonl.",
        "discovered_tools": discovered, "counts": args.counts, "modes": args.modes, "seed": args.seed,
        "warmups_per_case": args.warmups, "samples_per_case": args.samples, "delay_ms": args.delay_ms,
        "samples": samples, "errors": errors}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, default=str))
    valid = args.samples > 0 and len(samples) == len(cases) * args.samples and not errors and all(x["correct"] for x in samples)
    print(json.dumps({"output": str(args.output), "samples": len(samples), "all_correct": valid, "errors": len(errors)}))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
