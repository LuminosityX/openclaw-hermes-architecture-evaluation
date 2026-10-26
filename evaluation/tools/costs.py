#!/usr/bin/env python3
"""Calculate token-only USD estimates from explicit normalized usage and prices."""

import argparse
from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

from suite import require, unique_object

CATEGORIES = ('uncached_input', 'cache_read_input', 'cache_write_input', 'visible_output', 'reasoning_output')
COUNTERS = ('input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens', 'reasoning_tokens')


def amount(value):
    require(isinstance(value, (str, int)) and not isinstance(value, bool), 'USD values and rates must be decimal strings or integers')
    number = Decimal(value)
    require(number.is_finite() and number >= 0, 'USD values and rates must be finite and nonnegative')
    return number


def calculate_cost(usage, pricing, accepted_tasks=None):
    """Input includes cached input; output includes reasoning. All subcounts are disjoint."""
    require(pricing['currency'] == 'USD', 'Only USD snapshots are supported')
    require(pricing['billing_scheme'] == 'linear-token-categories', 'Tiered or other billing requires a specific calculator')
    date.fromisoformat(pricing['effective_date'])
    require(isinstance(pricing['source'], str) and pricing['source'].strip(), 'Price source is required')
    for field in ['provider', 'model']:
        require(isinstance(usage[field], str) and usage[field].strip() and usage[field] == pricing[field], f'Usage/price {field} mismatch')
    require(type(usage['complete']) is bool, 'Usage completeness must be explicit')
    if accepted_tasks is not None:
        require(type(accepted_tasks) is int and accepted_tasks >= 0, 'Accepted task count must be a nonnegative integer')
    reported = usage.get('provider_reported_cost_usd')
    result = dict(calculation_scope='model-token-charges-only', currency='USD',
                  provider_reported_cost_usd=None if reported is None else str(amount(reported)),
                  calculated_cost_usd=None, cost_per_accepted_task_usd=None,
                  price_effective_date=pricing['effective_date'], price_source=pricing['source'],
                  missing_reason=None)
    for name in COUNTERS:
        value = usage.get(name)
        require(value is None or (type(value) is int and value >= 0), f'Invalid token count: {name}')
    if not usage['complete'] or any(usage.get(k) is None for k in COUNTERS):
        result['missing_reason'] = 'Incomplete usage; unknown counters are not zero'
        return result
    uncached = usage['input_tokens'] - usage['cache_read_tokens'] - usage['cache_write_tokens']
    visible = usage['output_tokens'] - usage['reasoning_tokens']
    require(uncached >= 0 and visible >= 0, 'Overlapping token subcategories exceed inclusive totals')
    buckets = dict(zip(CATEGORIES, [uncached, usage['cache_read_tokens'], usage['cache_write_tokens'], visible, usage['reasoning_tokens']]))
    result['normalized_token_categories'] = buckets
    rates = pricing['usd_per_million_tokens']
    require(isinstance(rates, dict), 'Token rates must be an object')
    for key in CATEGORIES:
        if rates.get(key) is not None:
            amount(rates[key])
    missing = [key for key, count in buckets.items() if count and rates.get(key) is None]
    if missing:
        result['missing_reason'] = 'Missing price categories: ' + ', '.join(missing)
        return result
    total = sum((Decimal(count) * amount(rates[key]) / Decimal(1_000_000)
                 for key, count in buckets.items() if count), Decimal(0))
    result['calculated_cost_usd'] = str(total)
    if accepted_tasks:
        result['cost_per_accepted_task_usd'] = str(total / accepted_tasks)
    else:
        result['per_accepted_task_missing_reason'] = 'Accepted task count is unknown or zero'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--usage', type=Path, required=True)
    parser.add_argument('--pricing', type=Path, required=True)
    parser.add_argument('--accepted-tasks', type=int)
    args = parser.parse_args()
    try:
        usage = json.loads(args.usage.read_text(), object_pairs_hook=unique_object)
        pricing = json.loads(args.pricing.read_text(), object_pairs_hook=unique_object)
        print(json.dumps(calculate_cost(usage, pricing, args.accepted_tasks), indent=2))
    except (ValueError, KeyError, TypeError, OSError, InvalidOperation) as error:
        parser.exit(1, f'FAIL: {error}\n')


if __name__ == '__main__':
    main()
