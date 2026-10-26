"""Real token amortization retains failures, learning and unattributed calls."""
COUNTERS=['prompt_tokens','completion_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens']


def account(ledger,accepted):
    groups={name:dict(requests=0,known_usage={key:0 for key in COUNTERS},missing_counters={key:0 for key in COUNTERS}) for name in ['baseline','learning','reuse','unattributed']}
    for row in ledger['requests']:
        if not row.get('forwarded_to_transport'):continue
        stage=row.get('synthetic_input_observations',{}).get('reuse_stage') or ''
        name='learning' if stage=='LEARN' else 'baseline' if stage.startswith('BASELINE_TASK_') else 'reuse' if stage.startswith('REUSE_TASK_') else 'unattributed'
        group=groups[name];group['requests']+=1
        for key in COUNTERS:
            value=(row.get('usage') or {}).get(key)
            if type(value) is int and value>=0:group['known_usage'][key]+=value
            else:group['missing_counters'][key]+=1
    unfinished=max(0,ledger['forwarded_request_count']-sum(g['requests'] for g in groups.values()))
    groups['unattributed']['requests']+=unfinished
    for key in COUNTERS:groups['unattributed']['missing_counters'][key]+=unfinished
    normalized={}
    for arm in ['baseline','reuse']:
        denominator=accepted.get(arm,0);names=[arm,'learning'] if arm=='reuse' else [arm]
        normalized[arm]=dict(accepted_deliveries=denominator,known_tokens_per_accepted_delivery={key:sum(groups[n]['known_usage'][key] for n in names)/denominator if denominator and not any(groups[n]['missing_counters'][key] for n in names) else None for key in COUNTERS})
    return dict(kind='paired-reuse-provider-accounting',groups=groups,normalization=normalized,usage_synthetic=ledger['kind']!='real-provider-request-ledger',
        actual_charge_usd=None,monetary_break_even=None,
        rule='All failed and retried calls remain in each arm numerator; learning is charged to reuse. Unattributed calls remain explicit and in campaign totals. Cache counters partition input; actual invoice cost and monetary break-even remain unknown.')
