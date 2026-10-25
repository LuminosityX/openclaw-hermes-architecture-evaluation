#!/usr/bin/env python3
"""One real Hermes AIAgent conversation against the local scripted HTTP model."""
import argparse
import atexit
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def parse_tool_payload(content):
    # Inspect the native safety envelope as recorded; leave its original message intact.
    if isinstance(content, str) and content.startswith("<untrusted_tool_result ") and content.endswith("</untrusted_tool_result>"):
        content = content.split("\n\n", 1)[1].rsplit("\n</untrusted_tool_result>", 1)[0]
    return json.loads(content)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--prompt", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--phase", choices=["smoke", "measured"], default="smoke")
    p.add_argument("--mcp-case", "--mcp", action="store_true", help="Use native MCP discovery and a parallel-safe stdio bench_delay server.")
    args = p.parse_args()
    profile = ROOT / "runtime/hermes-agent-cases" / args.run_id
    profile.mkdir(parents=True, exist_ok=True)
    config = {"model": {"context_length": 128000}, "terminal": {"backend": "local", "cwd": str(ROOT)}, "background_review": {"enabled": False}}
    if args.mcp_case:
        config["mcp_servers"] = {"bench": {"command": "/usr/bin/python3", "args": [str(ROOT / "scripts/mcp_fixture.py")],
            "supports_parallel_tool_calls": True, "trust": "full", "lazy": False}}
        config["tools"] = {"tool_search": {"enabled": "off"}}
    (profile / "config.yaml").write_text(json.dumps(config, indent=2))
    os.environ["HERMES_HOME"] = str(profile)
    os.environ["HERMES_RUNTIME_DIR"] = str(profile / "runtime")
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "sources/hermes"))
    process_start = time.perf_counter_ns()
    from run_agent import AIAgent
    import psutil
    import_end = time.perf_counter_ns()
    discovered = []
    mcp_discovery_ms = 0
    if args.mcp_case:
        from tools.mcp_tool_discovery import discover_mcp_tools, is_mcp_tool_parallel_safe
        from tools.mcp_tool_lifecycle import shutdown_mcp_servers
        atexit.register(shutdown_mcp_servers, names={"bench"}, timeout=5)
        discovery_start = time.perf_counter_ns()
        discovered = discover_mcp_tools(["bench"])
        mcp_discovery_ms = (time.perf_counter_ns() - discovery_start) / 1e6
        if not any(name.endswith("bench_delay") and is_mcp_tool_parallel_safe(name) for name in discovered):
            raise RuntimeError("Native MCP discovery did not expose a parallel-safe bench_delay tool: " + repr(discovered))
    agent = AIAgent(api_key="bench-local", base_url=args.base_url, provider="custom", api_mode="chat_completions",
        model="bench-scripted", enabled_toolsets=["bench"] if args.mcp_case else ["terminal"], quiet_mode=True, skip_context_files=True,
        skip_memory=True, skip_background_review=True, max_iterations=8, cwd=str(ROOT))
    init_end = time.perf_counter_ns()
    process = psutil.Process()
    rss_initialized = process.memory_info().rss
    start = time.perf_counter_ns()
    try:
        result = agent.run_conversation(args.prompt)
        end = time.perf_counter_ns()
        commit = subprocess.check_output(["git", "-C", str(ROOT / "sources/hermes"), "rev-parse", "HEAD"], text=True).strip()
        tool_results = []
        for message in result.get("messages", []):
            if message.get("role") == "tool":
                try:
                    tool_results.append(parse_tool_payload(message["content"]))
                except (json.JSONDecodeError, TypeError) as exc:
                    tool_results.append({"_raw": message["content"], "_parse_error": str(exc)})
        expected_match = re.search(r"BENCH_TOOL_COUNT=(\d+)", args.prompt)
        expected_count = int(expected_match.group(1)) if expected_match else None
        if args.mcp_case:
            returned_records = [json.loads(x["result"]) if isinstance(x.get("result"), str) else x.get("result", {}) for x in tool_results]
            correct = bool(returned_records) and all(x.get("status") == "ok" and x.get("run_id") == args.run_id for x in returned_records)
            if expected_count is not None:
                correct = correct and len(returned_records) == expected_count and {x.get("id") for x in returned_records} == set(range(expected_count))
        else:
            correct = bool(tool_results) and all(x.get("exit_code") == 0 and not x.get("error") for x in tool_results) and (expected_count is None or len(tool_results) == expected_count)
        payload = {"framework": "hermes", "commit": commit, "phase": args.phase,
            "scope": "Actual AIAgent conversation using local scripted chat-completions HTTP model and native " + ("MCP stdio tools." if args.mcp_case else "terminal tools."), "correct": correct,
            "mcp_case": args.mcp_case, "discovered_mcp_tools": discovered, "mcp_discovery_ms": mcp_discovery_ms,
            "advertised_tools": [tool["function"]["name"] for tool in agent.tools],
            "parsed_tool_results": tool_results,
            "run_id": args.run_id, "prompt": args.prompt, "import_ms": (import_end-process_start)/1e6,
            "initialize_ms": (init_end-import_end)/1e6, "conversation_ms": (end-start)/1e6,
            "rss_initialized_bytes": rss_initialized, "rss_after_conversation_bytes": process.memory_info().rss,
            "final_response": result.get("final_response"), "messages": result.get("messages"),
            "result_keys": list(result)}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, default=str))
        print(json.dumps({"output": str(args.output), "final_response": result.get("final_response")}))
    finally:
        agent.close()
        if args.mcp_case:
            shutdown_mcp_servers(names={"bench"}, timeout=5)


if __name__ == "__main__":
    main()
