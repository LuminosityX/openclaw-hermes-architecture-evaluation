#!/usr/bin/env python3
"""Validate source archive integrity offline; never start product experiments."""

import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tomllib
from urllib.parse import unquote, urlsplit

from update_manifest import ROOT, archive_files, file_metadata


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def checked_path(name):
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and ".." not in relative.parts,
            f"Invalid repository path: {name}")
    path = ROOT / relative
    require(path.resolve().is_relative_to(ROOT), f"Path escapes repository: {name}")
    require(path.is_file() and not path.is_symlink(), f"Missing regular file: {name}")
    return path


def check_inventory():
    manifest = read_json(ROOT / "SOURCE_MANIFEST.json")
    require(manifest["version"] == "V6", "Only the V6 archive is supported")
    require(manifest["schema_version"] == 1, "Unsupported manifest schema")
    seen = set()
    for entry in manifest["files"]:
        name = entry["archive_path"]
        require(name.startswith("v6/") and name not in seen,
                f"Invalid or duplicate archive entry: {name}")
        seen.add(name)
        for key, value in file_metadata(checked_path(name)).items():
            require(entry[key] == value, f"Archive {key} mismatch: {name}")
    actual = {path.relative_to(ROOT).as_posix() for path in archive_files()}
    require(seen == actual,
            f"Archive inventory differs: missing={sorted(actual - seen)}, "
            f"stale={sorted(seen - actual)}")
    return len(seen)


def check_references():
    references = read_json(ROOT / "v6/references/source-index.json")
    for entry in references:
        data = checked_path(entry["archive_path"]).read_bytes()
        require(hashlib.sha256(data).hexdigest() == entry["sha256"],
                f"Upstream reference hash mismatch: {entry['claim_id']}")
    layout = read_json(ROOT / "HISTORICAL_LAYOUT.json")
    for destination in layout["roots"].values():
        path = ROOT / destination
        require(path.resolve().is_relative_to(ROOT) and path.exists(),
                f"Unresolved archive mapping: {destination}")
    revisions = read_json(ROOT / "v6/patches/source-revisions.json")
    for entry in revisions:
        if "patch" in entry:
            checked_path(entry["patch"])
    return len(references)


def check_windows_bundle():
    bundle = ROOT / "v6/windows-native-bundle"
    manifest = read_json(bundle / "bundle-manifest.json")
    for name, expected in manifest["files"].items():
        path = checked_path(f"v6/windows-native-bundle/{name}")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                f"Windows bundle hash mismatch: {name}")
    actual = {path.name for path in bundle.iterdir() if path.is_file()}
    require(actual == set(manifest["files"]) | {"bundle-manifest.json"},
            "Windows bundle inventory differs from its manifest")


def check_protocol():
    protocol = read_json(ROOT / "v6/protocol/protocol_v1.json")
    template = read_json(ROOT / "v6/protocol/observations_template.json")
    semantic = hashlib.sha256(json.dumps(
        protocol, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    require(semantic == template["protocol_semantic_sha256"],
            "Frozen protocol differs from the observation template")
    require(len(protocol["dimensions"]) == 11, "Expected eleven dimensions")
    for dimension in protocol["dimensions"]:
        require(sum(item["weight"] for item in dimension["criteria"]) == 100,
                f"Criterion weights do not sum to 100: {dimension['id']}")
    scorer = ROOT / "v6/protocol/score_protocol.py"
    require(hashlib.sha256(scorer.read_bytes()).hexdigest() == protocol["scorer_sha256"],
            "Frozen scorer hash differs from the protocol")
    result = subprocess.run(
        [sys.executable, str(scorer), "--selftest"],
        cwd=ROOT, check=True, capture_output=True, text=True, timeout=60,
    )
    tests = json.loads(result.stdout)
    require(tests["passed"] is True, "Scorer self-tests failed")
    return tests["checks"]


def check_documentation():
    documents = sorted(ROOT.glob("*.md")) + sorted((ROOT / "docs").rglob("*.md"))
    documents.append(ROOT / "v6/windows-native-bundle/README.md")
    for path in documents:
        text = path.read_text(encoding="utf-8")
        require(text.endswith("\n"), f"Missing final newline: {path.relative_to(ROOT)}")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target_path = (path.parent / unquote(parsed.path)).resolve()
            require(target_path.is_relative_to(ROOT) and target_path.exists(),
                    f"Broken local link in {path.relative_to(ROOT)}: {target}")
    return len(documents)


def check_source_files():
    patterns = {
        "API key": re.compile(rb"\bsk-[A-Za-z0-9]{24,}\b"),
        "GitHub token": re.compile(
            rb"\b(?:ghp_|gho_|ghu_|ghs_|github_pat_)[A-Za-z0-9_]{20,}\b"
        ),
        "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    }
    counts = {"python": 0, "json": 0, "toml": 0}
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if not path.is_file() or {".git", "__pycache__"} & set(relative.parts):
            continue
        require(path.name.isascii(), f"Non-ASCII filename: {relative}")
        data = path.read_bytes()
        for kind, pattern in patterns.items():
            require(not pattern.search(data), f"Potential {kind} in {relative}")
        require(path.suffix not in {".log", ".sqlite", ".db"},
                f"Generated execution data in repository: {relative}")
        require(not path.name.startswith(".env") or path.name in {".env.example", ".env.sample"},
                f"Environment credential file in repository: {relative}")
        if path.suffix == ".py":
            ast.parse(data, filename=str(relative))
            counts["python"] += 1
        elif path.suffix == ".json":
            read_json(path)
            counts["json"] += 1
        elif path.suffix == ".toml":
            tomllib.loads(data.decode("utf-8"))
            counts["toml"] += 1
    return counts


def main():
    require(sys.version_info >= (3, 11), "Python 3.11 or later is required")
    counts = check_source_files()
    archived = check_inventory()
    claims = check_references()
    check_windows_bundle()
    tests = check_protocol()
    documents = check_documentation()
    print(f"PASS: {archived} archive files, {claims} source claims, "
          f"{counts['python']} Python files, {counts['json']} JSON files, "
          f"{counts['toml']} TOML files, {documents} documentation files, "
          f"{tests} scorer self-tests")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, SyntaxError, subprocess.SubprocessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
