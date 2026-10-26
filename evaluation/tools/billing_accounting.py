"""Preserve provider partitions; dated estimates are never actual invoices."""
from datetime import datetime
from decimal import Decimal

PRICE=dict(source='https://api-docs.deepseek.com/quick_start/pricing/',checked_on_utc='2026-10-26',model='deepseek-flash',model_version='DeepSeek-V4.1-Flash-1017',currency='USD',unit_tokens=1000000,peak=dict(cache_hit='0.006',cache_miss='0.3',output='1.2'),off_peak=dict(cache_hit='0.003',cache_miss='0.15',output='0.6'),peak_schedule='Monday-Friday UTC [01:00,04:00) and [06:00,10:00), excluding Chinese public holidays; all other times off-peak',holiday_calendar='Not independently resolved: weekday peak-window requests retain both possible tariffs')


def nonnegative(value):return type(value) is int and value>=0


def account(ledger):
    rows=[]
    for index,record in enumerate(ledger['requests']):
        if record.get('forwarded_to_provider') is not True:continue
        usage=record.get('usage') or {};prompt=usage.get('prompt_tokens');output=usage.get('completion_tokens')
        hit=usage.get('prompt_cache_hit_tokens');miss=usage.get('prompt_cache_miss_tokens');reasoning=(usage.get('completion_tokens_details') or {}).get('reasoning_tokens')
        valid=all(v is None or nonnegative(v) for v in [prompt,output,hit,miss,reasoning])
        partition_known=all(nonnegative(v) for v in [prompt,hit,miss])
        partition_valid=not partition_known or hit+miss==prompt
        reasoning_valid=reasoning is None or output is None or reasoning<=output
        price=None;bounds=None;tariff=None
        if valid and partition_known and partition_valid and nonnegative(output):
            at=datetime.fromisoformat(record['started_at_utc']);candidate=at.weekday()<5 and (1<=at.hour<4 or 6<=at.hour<10)
            def estimate(rates):return str((Decimal(hit)*Decimal(rates['cache_hit'])+Decimal(miss)*Decimal(rates['cache_miss'])+Decimal(output)*Decimal(rates['output']))/1000000)
            if candidate:bounds=dict(lower_usd=estimate(PRICE['off_peak']),upper_usd=estimate(PRICE['peak']));tariff='weekday-peak-window-holiday-status-unresolved'
            else:price=estimate(PRICE['off_peak']);tariff='unambiguously-off-peak'
        rows.append(dict(ledger_index=index,task_id=record.get('task_id') or record.get('synthetic_input_observations',{}).get('owned_accounting_task_id'),attribution_method='native-prompt-task-marker' if record.get('task_id') else 'exclusive-owned-task-relay' if record.get('synthetic_input_observations',{}).get('owned_accounting_task_id') else 'unknown',response_id=record.get('response_id'),upstream_request_id=record.get('upstream_request_id'),input_tokens_inclusive=prompt,output_tokens_including_reasoning=output,cache_hit_input_subset=hit,cache_miss_input_subset=miss,reasoning_output_subset=reasoning,usage_known=record.get('usage') is not None,category_values_valid=valid,input_partition_known=partition_known,input_partition_valid=partition_valid,reasoning_subset_valid=reasoning_valid,calculated_usd=price,calculated_usd_bounds=bounds,tariff=tariff,provider_reported_usd=record.get('provider_reported_cost_usd'),invoice_reconciliation=None,owned_response_intervention=record.get('owned_response_intervention')))
    actual_attempts=ledger.get('real_provider_request_count',len(rows))
    if type(actual_attempts) is not int or actual_attempts<len(rows):raise ValueError('Provider admitted-attempt count disagrees with finalized records')
    unfinished=actual_attempts-len(rows)
    complete=bool(rows) and unfinished==0 and all(r['usage_known'] for r in rows)
    return dict(price_snapshot=PRICE,requests=rows,real_attempt_count=actual_attempts,unfinished_attempts_with_unknown_usage=unfinished,complete_usage_for_all_attempts=complete,
        # Unknown attempts forbid a misleading partial total presented as complete.
        input_tokens_inclusive=sum(r['input_tokens_inclusive'] for r in rows) if complete and all(nonnegative(r['input_tokens_inclusive']) for r in rows) else None,
        output_tokens_including_reasoning=sum(r['output_tokens_including_reasoning'] for r in rows) if complete and all(nonnegative(r['output_tokens_including_reasoning']) for r in rows) else None,
        calculated_usd=sum((Decimal(r['calculated_usd']) for r in rows),Decimal(0)).to_eng_string() if rows and unfinished==0 and all(r['calculated_usd'] is not None for r in rows) else None,
        provider_reported_usd=None,actual_invoice_usd=None,invoice_reconciliation_delta=None,account_balance_attribution='unknown; no exclusive-account assumption',
        rules=['cache hit/miss partition inclusive input; never add them again','reasoning is a subset of output; never add it again','all real attempts include discarded upstream replies','provider invoice absent remains unknown, including failed/cancelled calls'])
