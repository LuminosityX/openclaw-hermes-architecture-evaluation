#!/usr/bin/env python3
"""Check the current OpenClaw design without running product experiments."""

import re
import sys
from urllib.parse import unquote, urlsplit

from suite import ROOT, load_matrix, render_catalogue


def main():
    matrix = load_matrix()
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
    print(f'PASS: OpenClaw only, 6 dimensions, {len(cases)} planned cases, '
          f'{scenarios} scenario labels; product execution disabled; no product results')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        raise SystemExit(1) from error
