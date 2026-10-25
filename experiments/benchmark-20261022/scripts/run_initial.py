"""Run actual native modules sequentially and preserve every sample and diagnostic."""
import argparse
import json
import os
from pathlib import Path
import random
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / "envs/openclaw-toolchain/node_modules/node/bin/node"
TSX = ROOT / "envs/openclaw-toolchain/node_modules/tsx/dist/loader.mjs"
PYTHON = ROOT / "envs/hermes/bin/python"
ENV = dict(os.environ)
ENV["OPENCLAW_STATE_DIR"] = str(ROOT / "runtime/openclaw-probes")
ENV["DOCKER_HOST"] = "unix://" + str(ROOT / "runtime/docker/docker.sock")
ENV["PATH"] = str(NODE.parent) + os.pathsep + str(ROOT / "envs/docker/docker") + os.pathsep + ENV.get("PATH", "")

def run(command, label, cwd=None):
    start = time.time()
    result = subprocess.run([str(x) for x in command], cwd=cwd or ROOT, env=ENV, text=True, capture_output=True, timeout=600)
    (ROOT / "logs" / f"{label}.stdout.log").write_text(result.stdout)
    (ROOT / "logs" / f"{label}.stderr.log").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError(f"{label} failed {result.returncode}: {result.stderr[-1200:]}")
    for line in reversed(result.stdout.splitlines()):
        try:
            data = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    else:
        raise RuntimeError(f"{label} did not emit JSON; inspect log")
    print(json.dumps({"completed": label, "wall_seconds": round(time.time()-start, 3)}), flush=True)
    return data

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--sandbox", action="store_true")
    options = parser.parse_args()
    ENV["BENCH_SAMPLES"] = str(options.samples)
    ENV["BENCH_WARMUPS"] = str(options.warmups)
    rng = random.Random(20261022)
    jobs = [(framework, size) for framework in ["openclaw", "hermes"] for size in [10, 100, 500]]
    rng.shuffle(jobs)
    rows = []
    native = []
    for framework, size in jobs:
        if framework == "hermes":
            output = ROOT / "raw" / f"hermes-skills-{size}.json"
            run([PYTHON, ROOT / "scripts/hermes_probe.py", "--sizes", size, "--samples", options.samples, "--warmups", options.warmups, "--output", output], f"skills-hermes-{size}")
            data = json.loads(output.read_text())
            rows.extend(data["samples"])
            native.append({"framework": framework, "size": size, "entrypoints": data["native_entrypoints"], "cold_definition": data["cold_definition"], "scope": data["scope"]})
        else:
            samples = []
            for i in range(options.warmups + options.samples):
                data = run([NODE, "--import", TSX, ROOT / "scripts/openclaw_probe.mjs", "cold", size], f"skills-openclaw-{size}-cold-{i}", ROOT / "sources/openclaw")
                if not data["catalog_correct"] or not data["reads_correct"]:
                    raise RuntimeError(f"Incorrect OpenClaw skill result {size}: {data}")
                if i >= options.warmups:
                    rows.append({"framework": framework, "row": 23, "metric": "catalog_cold", "size": size, "sample": i-options.warmups, "duration_ms": data["discovery_ms"], "correct": data["catalog_correct"]})
                    samples.append(data)
            data = run([NODE, "--import", TSX, ROOT / "scripts/openclaw_probe.mjs", "warm", size], f"skills-openclaw-{size}-warm", ROOT / "sources/openclaw")
            for record in data["samples"]:
                if not record["catalog_correct"] or not record["reads_correct"]:
                    raise RuntimeError("Incorrect OpenClaw warm sample")
                rows.extend([
                    {"framework": framework, "row": 23, "metric": "catalog_warm", "size": size, "sample": record["sample"], "duration_ms": record["discovery_ms"], "correct": record["catalog_correct"]},
                    {"framework": framework, "row": 23, "metric": "read_three_warm", "size": size, "sample": record["sample"], "duration_ms": record["read_three_skills_ms"], "correct": record["reads_correct"]}])
            (ROOT / "raw" / f"openclaw-skills-{size}.json").write_text(json.dumps({"cold": samples, "warm": data["samples"]}, indent=2))
            native.append({"framework": framework, "size": size, "entrypoints": ["loadWorkspaceSkills(workspaceOnly=true)", "loadSingleSkillDirectory"], "cold_definition": "Fresh process and imported native modules before timer; OS page cache warm", "scope": "Native module, TypeScript source imported via tsx; not full agent/CLI/Gateway"})
        (ROOT / "results/skills-samples.partial.json").write_text(json.dumps(rows, indent=2))
    payload = {"schema_version": 1, "seed": 20261022, "block_order": jobs, "samples_per_case": options.samples, "warmups_per_case": options.warmups, "scope": "Native skill catalog/read modules. Imports excluded. Application-cache cold versus application-cache warm; OS cache warm. Discovery limits aligned to include all 500 fixtures. API read serialization differs and is documented.", "native": native, "samples": rows}
    (ROOT / "results/skills-samples.json").write_text(json.dumps(payload, indent=2))
    if options.sandbox:
        run([PYTHON, ROOT / "scripts/hermes_docker_probe.py", "--samples", options.samples, "--warmups", options.warmups], "sandbox-hermes")
        for mode in ["cold", "warm"]:
            data = run([NODE, "--import", TSX, ROOT / "scripts/openclaw_sandbox_probe.mjs", mode], f"sandbox-openclaw-{mode}", ROOT / "sources/openclaw")
            (ROOT / "raw" / f"openclaw-sandbox-{mode}.json").write_text(json.dumps(data, indent=2))
    print(json.dumps({"status": "complete", "skill_samples": len(rows)}), flush=True)

if __name__ == "__main__":
    main()
