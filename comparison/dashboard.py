#!/usr/bin/env python3
"""Render the repository progress ledger into the README; no network or experiments."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START = '<!-- comparison-dashboard:start -->'
END = '<!-- comparison-dashboard:end -->'
LABEL = {'planned': 'Planned', 'in_progress': 'In progress', 'blocked': 'Blocked',
         'done': 'Complete', 'not_applicable': 'Not applicable'}


def render():
    data = json.loads((ROOT / 'comparison/progress.json').read_text(encoding='utf-8'))
    if data['schema_version'] != 1 or data['products'] != ['Codex', 'DSH', 'OpenClaw']:
        raise ValueError('Unsupported ledger schema or products')
    audit = json.loads((ROOT / 'evaluation/campaigns/full-20261026-batched/completion-audit.json').read_text(encoding='utf-8'))['completion']
    counts = audit['scenario_counts']
    lines = [START, '## Research progress', '',
        'Each cell is a work item, not a success rate. Historical OpenClaw evidence is not counted as completed cross-product work.', '',
        '| Layer / experiment | Codex | DSH | OpenClaw |', '| --- | --- | --- | --- |']
    seen = set()
    for item in data['items']:
        if item['id'] in seen or item['layer'] not in ('platform', 'harness'):
            raise ValueError('Duplicate ID or invalid layer')
        seen.add(item['id'])
        if set(item['products']) != set(data['products']):
            raise ValueError('Each item must cover every product')
        cells = []
        for product in data['products']:
            entry = item['products'][product]
            status = entry['status']
            if status not in LABEL or not isinstance(entry['evidence'], list):
                raise ValueError('Invalid status or evidence')
            if status in ('done', 'not_applicable') and not entry['evidence']:
                raise ValueError('Completed or inapplicable entries require evidence')
            for name in entry['evidence']:
                p = (ROOT / name).resolve()
                if not p.is_relative_to(ROOT) or not p.is_file():
                    raise ValueError(f'Invalid evidence path: {name}')
            cells.append(LABEL[status])
        layer = 'Platform' if item['layer'] == 'platform' else 'Harness'
        lines.append(f"| {layer} · {item['id']} {item['name']} | " + ' | '.join(cells) + ' |')
    latest = data.get('latest_ci')
    if latest:
        url = latest['url']
        prefix = 'https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/'
        if not url.startswith(prefix) or not url[len(prefix):].isdigit() or latest['result'] not in ('success', 'failure', 'cancelled', 'skipped'):
            raise ValueError('Invalid CI progress record')
        lines += ['', f"**Latest session calibration:** {latest['result']} (aggregate of three independent runners). [View run and individual jobs]({url})."]
    lines += ['', f"**Frozen OpenClaw campaign:** {audit['measured_scenarios']}/{audit['scenarios']} scenarios measured; {counts['pass']} passed, {counts['fail']} retained failures, {counts['unsupported']} confirmed not applicable; {audit['accepted_observation_count']} independent observations. [Audit and evidence](evaluation/campaigns/full-20261026-batched/README.md).", '',
        'Generated from the [progress ledger](comparison/progress.json) and the frozen audit. GitHub Actions shows live job steps; session calibration results synchronize automatically. See [maintenance](comparison/README.md).', END]
    return '\n'.join(lines)


def render_visual():
    data = json.loads((ROOT / 'comparison/progress.json').read_text(encoding='utf-8'))
    colors = {'done': '#65e7c0', 'in_progress': '#7a9cff', 'planned': '#344363',
              'blocked': '#ffbd6a', 'not_applicable': '#8190aa'}
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 980 270" role="img" aria-labelledby="title desc">',
        '<title id="title">Cross-product architecture research progress</title>',
        '<desc id="desc">Work-item states from the repository ledger. Calibrations are not formal completion.</desc>',
        '<rect width="980" height="270" rx="18" fill="#0d1527"/>',
        '<circle cx="52" cy="52" r="8" fill="#65e7c0"><animate attributeName="opacity" values="1;0.35;1" dur="2.6s" repeatCount="indefinite"/></circle>',
        '<text x="72" y="58" fill="#f0f5ff" font-family="Arial,sans-serif" font-size="22" font-weight="700">ARCHITECTURE RESEARCH / WORK ITEM STATUS</text>',
        '<text x="52" y="88" fill="#a7b6d4" font-family="Arial,sans-serif" font-size="14">Platform + harness   •   ledger snapshot   •   not task success rates</text>']
    statuses = ['done', 'in_progress', 'blocked', 'not_applicable', 'planned']
    for row, product in enumerate(data['products']):
        counts = {status: sum(item['products'][product]['status'] == status for item in data['items']) for status in statuses}
        total = len(data['items'])
        y = 124 + row * 41
        out.append(f'<text x="52" y="{y+13}" fill="#e8efff" font-family="Arial,sans-serif" font-size="15" font-weight="700">{product}</text>')
        x = 185
        for status in statuses:
            width = 590 * counts[status] / total if total else 0
            if width:
                out.append(f'<rect x="{x:.2f}" y="{y}" width="{width:.2f}" height="16" fill="{colors[status]}" rx="3"/>')
            x += width
        out.append(f'<text x="800" y="{y+13}" fill="#b9c7e1" font-family="Arial,sans-serif" font-size="13">{counts["done"]} complete · {counts["in_progress"]} active</text>')
    out += ['<text x="52" y="257" fill="#a7b6d4" font-family="Arial,sans-serif" font-size="12">● COMPLETE     ● IN PROGRESS     ● PLANNED     |     LIVE JOBS: OPEN GITHUB ACTIONS</text>', '</svg>']
    return '\n'.join(out) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = ROOT / 'README.md'
    original = path.read_text(encoding='utf-8')
    if original.count(START) != 1 or original.count(END) != 1 or original.index(START) > original.index(END):
        raise ValueError('README dashboard markers missing or duplicated')
    updated = original[:original.index(START)] + render() + original[original.index(END) + len(END):]
    visual_path = ROOT / 'comparison/progress.svg'
    visual = render_visual()
    if args.check:
        if not visual_path.exists() or visual_path.read_text(encoding='utf-8') != visual:
            raise SystemExit('Progress visual is stale; run python3 comparison/dashboard.py')
        if updated != original:
            raise SystemExit('Dashboard is stale; run python3 comparison/dashboard.py')
        print('Dashboard is current')
    else:
        path.write_text(updated, encoding='utf-8')
        visual_path.write_text(visual, encoding='utf-8')


if __name__ == '__main__':
    main()
