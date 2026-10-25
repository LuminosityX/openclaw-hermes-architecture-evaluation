"""Create identical synthetic skills and expected checksums for both native loaders."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = {"schema_version": 1, "sizes": [10, 100, 500], "fixtures": []}
for size in manifest["sizes"]:
    skills_root = ROOT / "fixtures" / f"skills-{size}"
    skills_root.mkdir(parents=True, exist_ok=True)
    entries = []
    for i in range(size):
        name = f"bench-{i:04d}"
        directory = skills_root / name
        directory.mkdir(exist_ok=True)
        marker = hashlib.sha256(f"benchmark-v1:{size}:{name}".encode()).hexdigest()
        text = f'---\nname: {name}\ndescription: Validate synthetic record {i:04d} and return its checksum.\n---\n\n# Synthetic record validation\n\n'
        text += f"When invoked, read references/record.txt and report the marker exactly.\nExpected marker: {marker}\n\n"
        text += ("Validate inputs, preserve record identifiers, and return a deterministic JSON result.\n" * 55)
        skill = directory / "SKILL.md"
        skill.write_text(text)
        refs = directory / "references"
        refs.mkdir(exist_ok=True)
        (refs / "record.txt").write_text(f"record={i}\nmarker={marker}\n")
        entries.append({"name": name, "skill_sha256": hashlib.sha256(skill.read_bytes()).hexdigest(), "skill_bytes": skill.stat().st_size, "marker": marker})
    manifest["fixtures"].append({"size": size, "path": str(skills_root), "entries": entries})
manifest["actual_skill_file_bytes"] = sorted({e["skill_bytes"] for f in manifest["fixtures"] for e in f["entries"]})
(ROOT / "fixtures" / "manifest.json").write_text(json.dumps(manifest, indent=2))
print(json.dumps({"sizes": manifest["sizes"], "total_skills": sum(manifest["sizes"]), "manifest": str(ROOT / "fixtures" / "manifest.json")}))
