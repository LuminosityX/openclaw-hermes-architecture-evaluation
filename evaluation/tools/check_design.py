#!/usr/bin/env python3
"""Check the current designs without running product experiments."""

import json
import re
import sys
from urllib.parse import unquote, urlsplit

from suite import ROOT, load_matrix, render_catalogue, validate
from architecture import load_studies
from source_evidence import load_registry


def check_codex_matrix():
    path = ROOT / 'evaluation/design/codex-matrix.json'
    if not path.exists():
        return None
    codex = json.loads(path.read_text(encoding='utf-8'))
    validate(codex)
    openclaw = load_matrix()
    openclaw_counts = {e['id']: len(e['scenarios']) for d in openclaw['dimensions'] for e in d['experiments']}
    cases = [e for d in codex['dimensions'] for e in d['experiments']]
    for case in cases:
        if case.get('openclaw_case_ids') != [case['id']]:
            raise ValueError(f'Codex provenance mapping missing: {case["id"]}')
        if len(case['scenarios']) != openclaw_counts[case['id']]:
            raise ValueError(f'Scenario count differs from the OpenClaw inventory: {case["id"]}')
    return cases


def main():
    matrix = load_matrix()
    studies = load_studies()
    investigations=load_registry()
    catalogue = ROOT / 'evaluation/experiment-catalogue.md'
    if catalogue.read_text(encoding='utf-8') != render_catalogue(matrix):
        raise ValueError('Catalogue differs from the matrix; regenerate with suite.py catalogue')
    for path in (ROOT / 'evaluation').rglob('*.md'):
        text = path.read_text(encoding='utf-8')
        if not text.endswith('\n'):
            raise ValueError(f'Missing final newline: {path.relative_to(ROOT)}')
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', text):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            destination = (path.parent / unquote(parsed.path)).resolve()
            if not destination.is_relative_to(ROOT) or not destination.exists():
                raise ValueError(f'Broken evaluation link: {path.name}: {target}')
    cases = [e for d in matrix['dimensions'] for e in d['experiments']]
    scenarios = sum(len(e['scenarios']) for e in cases)
    codex_cases = check_codex_matrix()
    print(f'PASS: OpenClaw only, 6 dimensions, {len(cases)} planned cases, '
          f'{scenarios} scenario labels; {len(studies["studies"])} architecture studies; '
          f'{len(investigations["investigations"])} source-bound investigations; '
          'plan validation only; product conclusions require execution evidence'
          + (f'; Codex plan: {len(codex_cases)} families, {sum(len(e["scenarios"]) for e in codex_cases)} scenarios' if codex_cases else ''))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        raise SystemExit(1) from error
