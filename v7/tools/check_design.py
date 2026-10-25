#!/usr/bin/env python3
"""Check the V7 design contract without running product experiments."""

import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    matrix = json.loads((ROOT / "v7/design/evaluation-matrix.json").read_text())
    protocol = json.loads((ROOT / "v6/protocol/protocol_v1.json").read_text())
    require(matrix["status"] == "planned-not-executed", "This is a design-only branch")
    execution = matrix["execution"]
    for field in ["enabled", "allow_dependency_downloads", "allow_paid_model_calls"]:
        require(execution[field] is False, f"Execution gate must remain disabled: {field}")
    require(execution["run_count"] == 0, "No V7 product runs have been performed")
    require(len(execution["required_before_execution"]) >= 4, "Execution gates are missing")
    expected = {item["id"] for item in protocol["dimensions"]}
    dimensions = matrix["dimensions"]
    require(len(dimensions) == len(expected) == 11, "Expected eleven dimensions")
    require({item["id"] for item in dimensions} == expected, "Dimension IDs differ from V6")
    source_experiments = {item["id"] for item in protocol["experiments"]}
    seen = set()
    scenarios = 0
    catalogue = (ROOT / "v7/experiment-catalogue.md").read_text()
    for dimension in dimensions:
        require(dimension["review_gap"], f"Missing review gap: {dimension['id']}")
        require(set(dimension["v6_basis"]) <= source_experiments, "Unknown V6 basis")
        require(len(dimension["experiments"]) >= 4, "Missing mechanism families")
        for case in dimension["experiments"]:
            identifier = case["id"]
            require(identifier not in seen and identifier.startswith(dimension["id"] + "-"),
                    f"Invalid experiment identifier: {identifier}")
            seen.add(identifier)
            require(case["status"] == "planned", f"Unsupported result claim: {identifier}")
            for field in ["title", "mechanism", "intervention", "oracle"]:
                require(isinstance(case[field], str) and len(case[field]) >= 12,
                        f"Missing experimental detail: {identifier}/{field}")
            for field in ["scenarios", "metrics", "controls", "evidence"]:
                require(len(case[field]) >= 3, f"Insufficient detail: {identifier}/{field}")
            require(case["billing"] in {"deterministic-local-fixture", "real-usage-required"},
                    f"Unknown billing mode: {identifier}")
            require(f"### {identifier} — {case['title']}" in catalogue,
                    f"Catalogue and matrix disagree: {identifier}")
            require(not {"score", "winner", "result", "passed"} & set(case),
                    f"Planned case contains a result: {identifier}")
            scenarios += len(case["scenarios"])
    for path in (ROOT / "v7").rglob("*.md"):
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text()):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            destination = (path.parent / parsed.path).resolve()
            require(destination.is_relative_to(ROOT) and destination.exists(),
                    f"Broken design link: {path.name}: {target}")
    print(f"PASS: 11 dimensions, {len(seen)} planned experiment families, "
          f"{scenarios} scenario labels; execution disabled; no product results")


if __name__ == "__main__":
    main()
