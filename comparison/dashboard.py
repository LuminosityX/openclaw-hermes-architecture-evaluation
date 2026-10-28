#!/usr/bin/env python3
"""Render the repository progress ledger into the README; no network or experiments."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START = '<!-- comparison-dashboard:start -->'
END = '<!-- comparison-dashboard:end -->'
LABEL = {'planned': '待开始', 'in_progress': '进行中', 'blocked': '阻塞',
         'done': '已完成', 'not_applicable': '不适用'}


def render():
    data = json.loads((ROOT / 'comparison/progress.json').read_text(encoding='utf-8'))
    if data['schema_version'] != 1 or data['products'] != ['Codex', 'DSH', 'OpenClaw']:
        raise ValueError('Unsupported ledger schema or products')
    audit = json.loads((ROOT / 'evaluation/campaigns/full-20261026-batched/completion-audit.json').read_text(encoding='utf-8'))['completion']
    counts = audit['scenario_counts']
    lines = [START, '## 测评进度看板', '',
        '**三方新协议：** 下表为工作项状态，非实验成功率；历史 OpenClaw 结果不自动计入新协议。', '',
        '| 层次 / 工作项 | Codex | DSH | OpenClaw |', '| --- | --- | --- | --- |']
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
        layer = '平台' if item['layer'] == 'platform' else 'Harness'
        lines.append(f"| {layer} · {item['id']} {item['name']} | " + ' | '.join(cells) + ' |')
    latest = data.get('latest_ci')
    if latest:
        url = latest['url']
        prefix = 'https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/'
        if not url.startswith(prefix) or not url[len(prefix):].isdigit() or latest['result'] not in ('success', 'failure', 'cancelled', 'skipped'):
            raise ValueError('Invalid CI progress record')
        lines += ['', f"**最近一次会话校准：** {latest['result']}（三个独立 runner 的汇总）。[查看运行和各单元]({url})。"]
    lines += ['', f"**既有 OpenClaw 冻结实验：** {audit['measured_scenarios']}/{audit['scenarios']} 场景已测，{counts['pass']} 通过、{counts['fail']} 保留失败观察，{counts['unsupported']} 已确认不适用；{audit['accepted_observation_count']} 个独立观察。[审计与证据](evaluation/campaigns/full-20261026-batched/README.md)。", '',
        '看板由 [进度台账](comparison/progress.json) 和冻结审计生成，反映仓库最新提交，运行中状态需更新台账。详见 [维护说明](comparison/README.md)。', END]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = ROOT / 'README.md'
    original = path.read_text(encoding='utf-8')
    if original.count(START) != 1 or original.count(END) != 1 or original.index(START) > original.index(END):
        raise ValueError('README dashboard markers missing or duplicated')
    updated = original[:original.index(START)] + render() + original[original.index(END) + len(END):]
    if args.check:
        if updated != original:
            raise SystemExit('Dashboard is stale; run python3 comparison/dashboard.py')
        print('Dashboard is current')
    else:
        path.write_text(updated, encoding='utf-8')


if __name__ == '__main__':
    main()
