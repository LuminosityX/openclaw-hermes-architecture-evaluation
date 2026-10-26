"""Synthetic rates test accounting arithmetic; they are not real model prices."""

from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from costs import calculate_cost


class CostTests(unittest.TestCase):
    def setUp(self):
        self.usage = dict(provider='synthetic', model='fixture', complete=True, input_tokens=1000,
                          output_tokens=200, cache_read_tokens=300, cache_write_tokens=100,
                          reasoning_tokens=50, provider_reported_cost_usd='0.009')
        self.pricing = dict(provider='synthetic', model='fixture', currency='USD',
                            billing_scheme='linear-token-categories', effective_date='2026-10-26',
                            source='Synthetic fixture, not provider pricing',
                            usd_per_million_tokens=dict(uncached_input='2', cache_read_input='0.2',
                                                        cache_write_input='3', visible_output='8', reasoning_output='8'))

    def test_subcategories_not_double_counted_and_reported_cost_separate(self):
        result = calculate_cost(self.usage, self.pricing, accepted_tasks=2)
        self.assertEqual(Decimal(result['calculated_cost_usd']), Decimal('0.00316'))
        self.assertEqual(Decimal(result['cost_per_accepted_task_usd']), Decimal('0.00158'))
        self.assertEqual(result['provider_reported_cost_usd'], '0.009')
        self.assertEqual(result['normalized_token_categories']['uncached_input'], 600)

    def test_missing_usage_never_becomes_free(self):
        self.usage['reasoning_tokens'] = None
        result = calculate_cost(self.usage, self.pricing)
        self.assertIsNone(result['calculated_cost_usd'])
        self.assertIn('unknown counters', result['missing_reason'])

    def test_incomplete_usage_even_with_counters_is_unknown(self):
        self.usage['complete'] = False
        self.assertIsNone(calculate_cost(self.usage, self.pricing)['calculated_cost_usd'])

    def test_missing_rate_not_zero(self):
        del self.pricing['usd_per_million_tokens']['reasoning_output']
        result = calculate_cost(self.usage, self.pricing)
        self.assertIsNone(result['calculated_cost_usd'])
        self.assertIn('reasoning_output', result['missing_reason'])

    def test_zero_accepted_tasks_has_no_finite_unit_cost(self):
        result = calculate_cost(self.usage, self.pricing, accepted_tasks=0)
        self.assertIsNotNone(result['calculated_cost_usd'])
        self.assertIsNone(result['cost_per_accepted_task_usd'])

    def test_overlapping_totals_rejected(self):
        for field, value in [('input_tokens', 100), ('output_tokens', 40)]:
            with self.subTest(field=field):
                usage = dict(self.usage, **{field: value})
                with self.assertRaisesRegex(ValueError, 'subcategories'):
                    calculate_cost(usage, self.pricing)

    def test_unknown_or_invalid_prices_rejected(self):
        for value in ['NaN', 'Infinity', '-2', True, 1.2]:
            self.pricing['usd_per_million_tokens']['visible_output'] = value
            with self.subTest(value=value), self.assertRaises((ValueError, InvalidOperation)):
                calculate_cost(self.usage, self.pricing)

    def test_wrong_model_or_billing_scheme_rejected(self):
        self.pricing['model'] = 'different'
        with self.assertRaisesRegex(ValueError, 'model mismatch'):
            calculate_cost(self.usage, self.pricing)
        self.pricing['model'] = 'fixture'
        self.pricing['billing_scheme'] = 'tiered'
        with self.assertRaisesRegex(ValueError, 'specific calculator'):
            calculate_cost(self.usage, self.pricing)

    def test_invalid_token_values(self):
        for value in [True, -1, 1.5, '100']:
            self.usage['input_tokens'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Invalid token count'):
                calculate_cost(self.usage, self.pricing)


if __name__ == '__main__':
    unittest.main()
