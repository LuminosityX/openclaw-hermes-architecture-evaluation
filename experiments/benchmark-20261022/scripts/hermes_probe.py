#!/usr/bin/env python3
"""Run fixed-commit Hermes native skill catalog/read microbenchmarks, no model calls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/hermes"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sizes", nargs="+", type=int, default=[10, 100, 500])
    p.add_argument("--samples", type=int, default=30)
    p.add_argument("--warmups", type=int, default=5)
    p.add_argument("--seed", type=int, default=20261022)
    p.add_argument("--output", type=Path, default=ROOT / "raw/hermes-skills.json")
    args = p.parse_args()
    profile = ROOT / "fixtures/hermes-probe-profile"
    profile.mkdir(exist_ok=True)
    (profile / "config.yaml").write_text("skills:\n  external_dirs: []\n  disabled: []\n")
    os.environ["HERMES_HOME"] = str(profile)
    os.environ["HERMES_RUNTIME_DIR"] = str(ROOT / "runtime/hermes-probe")
    os.chdir(ROOT)
    sys.path.insert(0, str(SOURCE))
    from tools import skills_tool as native

    manifests = {x["size"]: x for x in json.loads((ROOT / "fixtures/manifest.json").read_text())["fixtures"]}
    commit = subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True).strip()
    rng = random.Random(args.seed)
    sizes = args.sizes[:]
    rng.shuffle(sizes)
    samples = []
    checks = []
    for size in sizes:
        fixture = ROOT / f"fixtures/skills-{size}"
        # Production exposes this override explicitly for embedding/tests; no source edits.
        native.SKILLS_DIR = fixture
        native.clear_skills_cache()
        names = {x["name"] for x in manifests[size]["entries"]}
        found = native.find_all_skills()
        check = {"size": size, "catalog_correct": {x["name"] for x in found} == names, "found_count": len(found), "reads": []}
        selected = [manifests[size]["entries"][i] for i in [0, size // 2, size - 1]]
        for entry in selected:
            result = json.loads(native.skill_view(entry["name"], preprocess=False))
            digest = hashlib.sha256(result.get("content", "").encode()).hexdigest()
            check["reads"].append({"name": entry["name"], "success": result.get("success"), "sha256": digest, "expected_sha256": entry["skill_sha256"], "correct": digest == entry["skill_sha256"]})
        checks.append(check)
        cases = ["catalog_cold", "catalog_warm", "read_three_warm"]

        def once(case, record, index):
            if case == "catalog_cold":
                native.clear_skills_cache()
            elif case == "catalog_warm":
                native.find_all_skills()  # ensure native catalog is primed; not timed
            start = time.perf_counter_ns()
            if case.startswith("catalog"):
                result = native.find_all_skills()
            else:
                result = [native.skill_view(x["name"], preprocess=False) for x in selected]
            elapsed = (time.perf_counter_ns() - start) / 1e6
            if case.startswith("catalog"):
                correct = {x["name"] for x in result} == names
            else:
                correct = all(hashlib.sha256(json.loads(value).get("content", "").encode()).hexdigest() == entry["skill_sha256"] for value, entry in zip(result, selected))
            if record:
                samples.append({"framework": "hermes", "row": 23, "metric": case, "size": size, "sample": index, "duration_ms": elapsed, "correct": correct})

        for case in cases:
            for i in range(args.warmups):
                once(case, False, i)
        order = [(case, i) for case in cases for i in range(args.samples)]
        rng.shuffle(order)
        for case, index in order:
            once(case, True, index)
    payload = {"schema_version": 1, "framework": "hermes", "commit": commit, "python": sys.version,
        "scope": "Native module microbenchmark; not full agent, CLI, gateway, model, or OS cold boot.",
        "native_entrypoints": ["tools.skills_tool.find_all_skills", "tools.skills_tool.clear_skills_cache", "tools.skills_tool.skill_view(preprocess=False)"],
        "fixture_binding": "Set production-supported SKILLS_DIR override to shared fixture; HERMES_HOME and config isolated; exact namespace equality checked.",
        "cold_definition": "Native catalog cache cleared before call; imports and operating-system file cache remain warm.",
        "warm_definition": "Native catalog primed before call in same process, with unchanged fixtures.",
        "read_definition": "Read first/middle/last SKILL.md via native skill_view with preprocessing disabled; total time for 3 reads including JSON serialization; JSON decoding/checksums excluded from timing.",
        "seed": args.seed, "samples_per_case": args.samples, "warmups_per_case": args.warmups,
        "checks": checks, "samples": samples}
    args.output.parent.mkdir(exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2))
    valid = all(x["catalog_correct"] and all(r["correct"] for r in x["reads"]) for x in checks) and all(x["correct"] for x in samples)
    print(json.dumps({"output": str(args.output), "samples": len(samples), "all_correct": valid}))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
