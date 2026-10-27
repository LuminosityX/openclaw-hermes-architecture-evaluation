#!/usr/bin/env python3
"""Product-specific validation profiles shared by the matrix tooling.

Structural rules in suite.py stay product-agnostic; each pinned product carries
its own release-format expectations here. Registering a product never enables
execution. It only describes how that product's frozen design must look, so a
Codex matrix cannot weaken the OpenClaw campaign's validation and vice versa.
"""

VERSION_REGEX = {
    # Calendar versions like 2026.10.7 (OpenClaw releases).
    'openclaw': r'[0-9]{4}\.[0-9]+\.[0-9]+(?:-[0-9]+)?',
    # SemVer like 0.164.0 (Codex releases).
    'codex': r'[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.]+)?',
}


def _unscoped_tarball(package):
    return lambda version: f'https://registry.npmjs.org/{package}/-/{package}-{version}.tgz'


def _scoped_tarball(scope, name):
    return lambda version: f'https://registry.npmjs.org/{scope}/-/{name}-{version}.tgz'


PROFILES = {
    'openclaw': dict(
        product='openclaw',
        product_display='OpenClaw',
        matrix_link='design/evaluation-matrix.json',
        repo_slug='openclaw/openclaw',
        version_regex=VERSION_REGEX['openclaw'],
        tag_for=lambda version: 'v' + version,
        tarball_for=_unscoped_tarball('openclaw'),
        provenance_kind='legacy-v6',
        historical_reference_expect={
            'branch': 'archive/v6',
            'commit': 'a33644efc9490ff771d058ebf047f08550e4ccb3',
        },
        catalogue_title='OpenClaw experiment catalogue',
        plan_help='never run OpenClaw',
        notes='legacy_ids must map the 46 frozen V6 experiments exactly once.',
    ),
    'codex': dict(
        product='codex',
        product_display='Codex',
        matrix_link='design/codex-matrix.json',
        repo_slug='openai/codex',
        version_regex=VERSION_REGEX['codex'],
        tag_for=lambda version: 'rust-v' + version,
        tarball_for=_scoped_tarball('@openai/codex', 'codex'),
        provenance_kind='openclaw-cases',
        historical_reference_expect={
            'openclaw_campaign': 'evaluation/campaigns/full-20261026-batched',
            'openclaw_matrix': 'evaluation/design/evaluation-matrix.json',
        },
        catalogue_title='Codex experiment catalogue',
        plan_help='never run Codex',
        notes='every family records openclaw_case_ids (identity mapping to the completed OpenClaw campaign in this repository).',
    ),
}


def profile_for(product):
    profile = PROFILES.get(product)
    if profile is None:
        raise ValueError(
            f'No validation profile for product: {product}; add one in product_profiles.py '
            'with explicit release-format rules instead of weakening validation')
    return profile
