#!/usr/bin/env python3
"""Regenerate public progress from accepted, provenance-bound observations."""
from collections import Counter
import json
import re

from campaign import DEFAULT_PLAN, audit, load_plan, records_from
from suite import ROOT


def update():
    plan=load_plan()
    records=records_from(DEFAULT_PLAN.parent/'results')
    report=audit(plan,records)
    done=report['measured_scenarios']; remaining=len(report['missing_or_invalid_scenarios'])
    observations=report['accepted_observation_count']; counts=report['scenario_counts']
    status=(f'{done} of 257 scenarios have completed formal cloud execution'
            f'](evaluation/campaigns/full-20261026-batched/README.md), with {observations} independent observations: '
            f'{counts.get("pass",0)} scenarios pass and {counts.get("fail",0)} retain failed acceptance observations. '
            f'Another {remaining} scenarios remain incomplete. Running batches and missing adapters are not counted. '
            'Unified architecture analysis remains locked until the complete execution audit passes.')
    readme=ROOT/'README.md'
    text=readme.read_text()
    text=re.sub(r'\*\*Status:\*\* .*?(?=\n\n)', '**Status:** ['+status,text,flags=re.S)
    readme.write_text(text)
    progress=DEFAULT_PLAN.parent/'README.md'
    text=progress.read_text()
    suffix=text[text.index('Passing conditions apply'):]
    usage_path=DEFAULT_PLAN.parent/'provider-usage-totals.json'
    if usage_path.exists():
        usage=json.loads(usage_path.read_text());sums=usage['known_provider_usage_sums']
        paragraph=('The [provider accounting totals](provider-usage-totals.json) retain '
            f'{usage["formal_task_units"]} real-provider experiment units and {usage["real_provider_requests"]} requests, '
            f'with {sums["prompt_tokens"]:,} known inclusive input tokens and {sums["completion_tokens"]:,} known output tokens. '
            f'Known cache-hit input is {sums["prompt_cache_hit_tokens"]:,} and cache-miss input is {sums["prompt_cache_miss_tokens"]:,}; '
            'these partition input rather than add to it. Missing counters remain explicit in the accounting record. '
            'Actual invoiced charges remain unknown; no campaign monetary ceiling is set. These counters do not complete COST-07.')
        suffix=re.sub(r'The \[provider accounting (?:record|totals)\].*?(?=\n\n)',paragraph,suffix,flags=re.S)
    header=('# Formal OpenClaw campaign progress\n\n'
        f'The [active frozen plan](plan.json) has **{done}/257 scenarios completed**, with '
        f'**{observations} independent observations**. {counts.get("pass",0)} scenarios pass and '
        f'{counts.get("fail",0)} retain failure observations. Another {remaining} remain incomplete. '
        'Only accepted formal records count. Architecture interpretation remains deferred.\n\n'
        'Native OpenClaw is pinned to `'+plan['target']['version']+'`, source `'+plan['target']['source_commit']+'`. '
        'Each scenario completes its prescribed three or six independent units on disposable GitHub-hosted runners.\n\n'
        '| Family | Completed scenarios | Independent observations | Hosted runs |\n'
        '| --- | ---: | ---: | --- |\n')
    valid=[r for r in records if r['state'] in {'pass','fail'}]
    for case in plan['cases']:
        scenarios=[s for s in report['scenario_status'] if s['case_id']==case['id'] and s['state'] in {'pass','fail'}]
        if not scenarios: continue
        ids={s['id'] for s in scenarios}
        rows=[r for r in valid if r['scenario_id'] in ids]
        runs=sorted({str(r['run_id']) for r in rows})
        links=', '.join(f'[{run}](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/{run})' for run in runs)
        header+=f'| {case["id"]} {case["title"]} | {len(scenarios)} | {len(rows)} | {links} |\n'
    header+='\n| Required dimension | Formal scenarios completed / planned |\n| --- | ---: |\n'
    for dimension,planned in Counter(s['dimension'] for s in report['scenario_status']).items():
        completed=sum(s['dimension']==dimension and s['state'] in {'pass','fail'} for s in report['scenario_status'])
        header+=f'| {dimension} | {completed} / {planned} |\n'
    failures=[s['id'] for s in report['scenario_status'] if s['state']=='fail']
    header+='\nScenarios retaining failed acceptance observations: '+(', '.join(failures) or 'none')+'. '
    header+='These are execution results; source-backed architectural diagnosis remains deferred.\n\n'
    progress.write_text(header+suffix)
    print(f'{done}/257 scenarios, {observations} observations; {remaining} remaining')


if __name__=='__main__': update()
