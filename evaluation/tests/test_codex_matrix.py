"""Codex design-matrix integrity tests: structure inheritance, provenance and reproducibility."""

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

from suite import validate
from build_codex_matrix import OUTPUT, PIN, SOURCE_MATRIX, TRANSLATION, build


class CodexMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = json.loads(OUTPUT.read_text(encoding='utf-8'))
        validate(cls.matrix)
        cls.openclaw = json.loads(SOURCE_MATRIX.read_text(encoding='utf-8'))

    def test_product_scope_and_target_pin(self):
        self.assertEqual(self.matrix['scope']['products'], ['codex'])
        self.assertEqual(self.matrix['target']['product'], 'codex')
        pin = json.loads(PIN.read_text(encoding='utf-8'))
        for field in ('version', 'source_commit', 'release_tag', 'npm_integrity', 'npm_tarball'):
            self.assertEqual(self.matrix['target'][field], pin[field])
        self.assertNotIn('legacy_ids', json.dumps(self.matrix))

    def test_all_families_and_scenarios_preserved(self):
        openclaw_counts = {e['id']: len(e['scenarios']) for d in self.openclaw['dimensions'] for e in d['experiments']}
        codex_counts = {e['id']: len(e['scenarios']) for d in self.matrix['dimensions'] for e in d['experiments']}
        self.assertEqual(len(codex_counts), 60)
        self.assertEqual(sum(codex_counts.values()), 257)
        self.assertEqual(codex_counts, openclaw_counts)
        for dimension in self.matrix['dimensions']:
            for case in dimension['experiments']:
                self.assertEqual(case['product'], 'codex')
                self.assertEqual(case['openclaw_case_ids'], [case['id']])
                self.assertEqual(case['billing'], next(
                    e['billing'] for d in self.openclaw['dimensions'] for e in d['experiments'] if e['id'] == case['id']))
                self.assertEqual(case['coverage'], next(
                    e['coverage'] for d in self.openclaw['dimensions'] for e in d['experiments'] if e['id'] == case['id']))

    def test_translation_covers_every_family_with_a_codex_mechanism(self):
        translation = json.loads(TRANSLATION.read_text(encoding='utf-8'))
        known = {e['id'] for d in self.openclaw['dimensions'] for e in d['experiments']}
        self.assertEqual(set(k for k in translation if not k.startswith('_')), known)
        for identifier in known:
            self.assertGreaterEqual(len(translation[identifier]['mechanism'].strip()), 12,
                                    f'Mechanism too short: {identifier}')
            mechanism = next(e['mechanism'] for d in self.matrix['dimensions'] for e in d['experiments'] if e['id'] == identifier)
            self.assertEqual(mechanism, translation[identifier]['mechanism'])

    def test_no_product_results_embedded(self):
        for dimension in self.matrix['dimensions']:
            for case in dimension['experiments']:
                self.assertNotIn('score', case)
                self.assertNotIn('result', case)
                self.assertEqual(case['status'], 'planned')
                self.assertEqual(case['adapter_status'], 'not-implemented')

    def test_build_is_reproducible_from_reviewed_inputs(self):
        translation = json.loads(TRANSLATION.read_text(encoding='utf-8'))
        pin = json.loads(PIN.read_text(encoding='utf-8'))
        rebuilt = build(translation, pin)
        self.assertEqual(json.dumps(rebuilt, sort_keys=True), json.dumps(self.matrix, sort_keys=True))


if __name__ == '__main__':
    unittest.main()
