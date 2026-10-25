import json
from pathlib import Path
p=Path("result.json")
assert p.exists(), "MISSING_RESULT: generate result.json then run check.py again"
x=json.loads(p.read_text())
assert isinstance(x,dict)
print("RESULT_PRESENT")
