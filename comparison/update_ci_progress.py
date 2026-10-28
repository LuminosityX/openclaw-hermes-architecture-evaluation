#!/usr/bin/env python3
"""Record the completed hosted calibration without declaring formal coverage."""
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent.parent
result = os.environ['COMPARISON_RESULT']
run_id = os.environ['GITHUB_RUN_ID']
if result not in {'success', 'failure', 'cancelled', 'skipped'} or not run_id.isdigit():
    raise ValueError('Unexpected CI result or run ID')
path = root / 'comparison/progress.json'
data = json.loads(path.read_text(encoding='utf-8'))
data['latest_ci'] = {'result': result, 'url': 'https://github.com/zyw02/agent-architecture-evaluation/actions/runs/' + run_id}
for item in data['items']:
    if item['id'] == 'H05':
        for product in ('DSH', 'OpenClaw'):
            item['products'][product]['status'] = 'in_progress'
            item['products'][product]['note'] = 'Three-unit hosted calibration: ' + result + '; formal protocol remains incomplete.'
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
subprocess.run(['python3', str(root / 'comparison/dashboard.py')], check=True)
