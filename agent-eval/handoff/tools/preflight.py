#!/usr/bin/env python3
"""Read-only, no network or model invocation, no secret discovery."""
import json, platform, shutil, sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = {
    "python": sys.version.split()[0],
    "os": platform.system(), "architecture": platform.machine(),
    "executables": {x: shutil.which(x) for x in ["openclaw", "hermes", "codex", "dsh", "node", "npm", "pnpm", "docker", "git"]},
    "authorization_record_exists": (root / "records/authorization.json").is_file(),
    "note": "Presence is not readiness. No versions, credentials, accounts, network or models were probed."
}
print(json.dumps(out, ensure_ascii=False, indent=2))
