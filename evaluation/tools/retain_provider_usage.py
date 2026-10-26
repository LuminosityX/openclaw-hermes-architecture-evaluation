#!/usr/bin/env python3
"""Keep cloud-only provider counters, including failed paid calls, without raw prompts."""
import argparse
import hashlib
import json

from campaign import DEFAULT_PLAN,load_plan
from retain_campaign_results import api,bounded_archive,ARTIFACT_LIMIT,REPOSITORY
from suite import ROOT,require

COUNTERS=['prompt_tokens','completion_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens']


def summarize(files,artifact_url):
    result=dict(formal_task_units=0,real_provider_requests=0,response_models=[],
        known_provider_usage_sums={k:0 for k in COUNTERS},requests_missing_counter={k:0 for k in COUNTERS},
        requests_without_complete_usage=0,sources=[])
    models=set()
    for path,raw in files.items():
        if not path.endswith('provider-usage.json'):continue
        ledger=json.loads(raw)
        if ledger.get('kind')!='real-provider-request-ledger':continue
        requests=[r for r in ledger['requests'] if r.get('real_provider_call') is True and r.get('forwarded_to_provider') is True]
        forwarded=ledger['real_provider_request_count']
        require(type(forwarded) is int and forwarded>=len(requests),'Real provider ledger request count disagrees')
        result['formal_task_units']+=1;result['real_provider_requests']+=forwarded
        unfinished=forwarded-len(requests);result['requests_without_complete_usage']+=unfinished
        for key in COUNTERS:result['requests_missing_counter'][key]+=unfinished
        for request in requests:
            usage=request.get('usage') or {}
            result['requests_without_complete_usage']+=request.get('usage_complete') is not True
            if request.get('response_model'):models.add(request['response_model'])
            for key in COUNTERS:
                value=usage.get(key)
                if type(value) is int and value>=0:result['known_provider_usage_sums'][key]+=value
                else:result['requests_missing_counter'][key]+=1
        result['sources'].append(dict(reference=artifact_url+'#'+path,sha256=hashlib.sha256(raw).hexdigest()))
    result['response_models']=sorted(models)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-id',required=True,type=int);args=parser.parse_args()
    plan=load_plan();path=DEFAULT_PLAN.parent/'provider-usage-totals.json'
    baseline=DEFAULT_PLAN.parent/'provider-usage-accounting.json'
    original=json.loads(baseline.read_text())
    journal=json.loads(path.read_text()) if path.exists() else dict(batches={str(original['github_run_id']):dict(original,
        baseline_reference=baseline.name,baseline_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest())})
    run=str(args.run_id)
    if run not in journal['batches']:
        metadata=json.loads(api('actions/runs/'+run));require(metadata['status']=='completed','Wait for provider ledger completion')
        artifacts=json.loads(api('actions/runs/'+run+'/artifacts?per_page=100'))['artifacts'];summaries=[]
        for artifact in artifacts:
            if not artifact['name'].startswith('campaign-'):continue
            require(not artifact['expired'] and artifact['size_in_bytes']<=ARTIFACT_LIMIT,'Provider evidence expired or exceeded its bound')
            files=bounded_archive(api('actions/artifacts/'+str(artifact['id'])+'/zip'))
            url='https://github.com/'+REPOSITORY+'/actions/runs/'+run+'/artifacts/'+str(artifact['id'])
            summary=summarize(files,url)
            if summary['formal_task_units']:summaries.append(summary)
        if summaries:
            batch=dict(github_run_id=run,formal_task_units=sum(s['formal_task_units'] for s in summaries),
                real_provider_requests=sum(s['real_provider_requests'] for s in summaries),
                response_models=sorted({m for s in summaries for m in s['response_models']}),
                known_provider_usage_sums={k:sum(s['known_provider_usage_sums'][k] for s in summaries) for k in COUNTERS},
                requests_missing_counter={k:sum(s['requests_missing_counter'][k] for s in summaries) for k in COUNTERS},
                requests_without_complete_usage=sum(s['requests_without_complete_usage'] for s in summaries),
                sources=[ref for s in summaries for ref in s['sources']])
            journal['batches'][run]=batch
    batches=list(journal['batches'].values())
    journal.update(kind='campaign-real-provider-usage-accounting',
        purpose='All retained real-provider task attempts, including failed/harness-error calls; not COST-07 completion',
        formal_task_units=sum(b['formal_task_units'] for b in batches),real_provider_requests=sum(b['real_provider_requests'] for b in batches),
        known_provider_usage_sums={k:sum(b['known_provider_usage_sums'][k] for b in batches) for k in COUNTERS},
        requests_missing_counter={k:sum(b['requests_missing_counter'][k] for b in batches) for k in COUNTERS},
        requests_without_complete_usage=sum(b['requests_without_complete_usage'] for b in batches),
        cache_note='Cache hit/miss partition inclusive prompt tokens; never add them to prompt_tokens.',
        reasoning_note='Provider reasoning counters, where available, are part of output rather than additional tokens.',
        actual_charge_usd=None,invoice_reconciliation=None,campaign_spend_ceiling=None,
        raw_prompts_retained=False,raw_responses_retained=False,credentials_retained=False)
    data=json.dumps(journal,ensure_ascii=False,separators=(',',':'))+'\n'
    total=sum(p.stat().st_size for p in (ROOT/'evaluation/campaigns').rglob('*') if p.is_file())
    total-=path.stat().st_size if path.exists() else 0
    require(total+len(data.encode())<=plan['resource_policy']['maximum_local_campaign_evidence_bytes'],'Provider summary would exceed the 4 MiB evidence budget')
    path.write_text(data)
    print(json.dumps({k:journal[k] for k in ['formal_task_units','real_provider_requests','known_provider_usage_sums','requests_without_complete_usage','actual_charge_usd']}))


if __name__=='__main__':main()
