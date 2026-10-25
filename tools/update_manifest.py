#!/usr/bin/env python3
"""Refresh archive checksums without executing archived experiment code."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def file_metadata(path):
    data = path.read_bytes()
    return {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "git_blob_sha": hashlib.sha1(
            b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        ).hexdigest(),
    }


def archive_files():
    return sorted(
        path for path in (ROOT / "v6").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def main():
    path = ROOT / "SOURCE_MANIFEST.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    previous = {entry["archive_path"]: entry for entry in manifest["files"]}
    entries = []
    for source in archive_files():
        if source.is_symlink():
            raise ValueError(f"Archive symlinks are not supported: {source}")
        name = source.relative_to(ROOT).as_posix()
        entry = dict(previous.get(name, {}))
        current = file_metadata(source)
        if entry.get("sha256") and entry["sha256"] != current["sha256"]:
            entry.setdefault("original_sha256", entry["sha256"])
        entry.update(archive_path=name, **current)
        entries.append(entry)
    manifest.update(schema_version=1, scope="v6/**", files=entries)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Updated archive inventory: {len(entries)} files")


if __name__ == "__main__":
    main()
