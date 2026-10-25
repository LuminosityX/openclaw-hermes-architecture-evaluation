"""Immutable receipt audit for E03/E13, retaining original completeness flags."""
import hashlib,json,math
from runtime import R,save
from reconcile_usage import numbers

def audit(run):
 events=[json.loads(x) for x in (run/'api-audit.jsonl').read_text().splitlines()];requests={x['call']:x for x in events if x['event']=='request'};responses={x['call']:x for x in events if x['event']=='response'};rows=[]
 for call,request in requests.items():
  meta=responses.get(call,{});raw=run/f'api-response-{call:03}.raw';req=run/f'api-request-{call:03}.json';body=json.loads(req.read_text()) if req.exists() else {};usage=meta.get('usage') or {};ok=meta.get('usage_completeness')=='terminal_observed' and numbers(usage);corrected=False
  if not ok and not body.get('stream') and raw.exists() and meta.get('http_status')==200 and not meta.get('transport_failure'):
   try:b=json.loads(raw.read_bytes())
   except (ValueError,UnicodeDecodeError):b={}
   choices=b.get('choices',[]);corrected=bool(b.get('object')=='chat.completion' and choices and all(x.get('finish_reason') is not None for x in choices) and b.get('usage')==usage and numbers(usage));ok=corrected
  cost=(usage.get('prompt_tokens',0)-usage.get('prompt_cache_hit_tokens',0)+usage.get('prompt_cache_hit_tokens',0)*.02+usage.get('completion_tokens',0)*4)/1000000 if numbers(usage) else None
  if cost is not None and meta.get('estimated_cost_CNY') is not None and not math.isclose(cost,meta['estimated_cost_CNY'],abs_tol=1e-10):raise RuntimeError('Usage/fee mismatch')
  rows.append(dict(call=call,billing_complete=ok,original_completeness=meta.get('usage_completeness'),nonstream_flag_correction=corrected,fee=meta.get('estimated_cost_CNY'),raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest() if raw.exists() else None))
 return dict(run=str(run.relative_to(R)),all_calls=len(requests),all_responses=len(responses),incomplete=not rows or len(requests)!=len(responses) or not all(x['billing_complete'] for x in rows),observed_fee=sum(x['fee'] or 0 for x in rows),calls=rows,scope='All original request/response receipts, including auxiliary/training/failure/retry calls. No original usage flag or price is rewritten; missing usage is unknown, not zero cost.')

def main():
 rows=[]
 for root in ['runs-attacks','runs-reuse']:
  for result in sorted((R/root).glob('*/*/result.json')):
   run=result.parent
   if (run/'api-audit.jsonl').exists():rows.append(audit(run))
 save(R/'results/additional-usage-reconciliation.json',rows);print('ADDITIONAL_LEDGER_AUDIT',len(rows),'incomplete',sum(x['incomplete'] for x in rows))
if __name__=='__main__':main()
