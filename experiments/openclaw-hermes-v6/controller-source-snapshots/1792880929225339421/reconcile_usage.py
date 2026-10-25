"""Recover billing completeness from immutable raw receipts, without re-running products or changing fees.
The original recorder recognized SSE [DONE] but missed complete non-stream Chat JSON terminal choices.
"""
import hashlib,json,math
from pathlib import Path
from runtime import R,save

def numbers(usage):
 keys=['prompt_tokens','completion_tokens','total_tokens']
 return all(type(usage.get(k)) is int and usage[k]>=0 for k in keys) and usage['total_tokens']==usage['prompt_tokens']+usage['completion_tokens'] and type(usage.get('prompt_cache_hit_tokens',0)) is int and 0<=usage.get('prompt_cache_hit_tokens',0)<=usage['prompt_tokens']
def one(run):
 source=(run/'result.json').read_bytes();result=json.loads(source);calls=[];source_hash=hashlib.sha256(source).hexdigest();raw_signature={str(z['call']):[q.stat().st_size,q.stat().st_mtime_ns] if (q:=run/f"api-response-{z['call']:03}.raw").exists() else None for z in result.get('responses',[])};cache=run/'usage-reconciliation.json'
 if cache.exists():
  previous=json.loads(cache.read_text())
  if previous.get('source_result_sha256')==source_hash and previous.get('raw_signature')==raw_signature:return previous
 for meta in result.get('responses',[]):
  call=meta['call'];req=run/f'api-request-{call:03}.json';raw=run/f'api-response-{call:03}.raw';request=json.loads(req.read_text()) if req.exists() else {};usage=meta.get('usage',{});complete=meta.get('usage_completeness')=='terminal_observed' and numbers(usage);reason='observed stream terminal and internally consistent aggregate usage' if complete else 'unconfirmed; retained conservatively';corrected=False
  if not complete and not request.get('stream') and raw.exists() and meta.get('http_status')==200 and not meta.get('transport_failure'):
   try:body=json.loads(raw.read_bytes())
   except (ValueError,UnicodeDecodeError):body={}
   choices=body.get('choices',[])
   if body.get('object')=='chat.completion' and choices and all(c.get('finish_reason') is not None for c in choices) and body.get('usage')==usage and numbers(usage):complete=True;corrected=True;reason='Complete non-stream Chat JSON with terminal choices and exact matching aggregate usage; no SSE sentinel is required.'
  cost=(usage.get('prompt_tokens',0)-usage.get('prompt_cache_hit_tokens',0)+usage.get('prompt_cache_hit_tokens',0)*.02+usage.get('completion_tokens',0)*4)/1000000 if numbers(usage) else None
  if cost is not None and meta.get('estimated_cost_CNY') is not None and not math.isclose(cost,meta['estimated_cost_CNY'],rel_tol=1e-10,abs_tol=1e-10):raise RuntimeError('Price/usage reconciliation mismatch; do not silently rewrite billing')
  calls.append(dict(call=call,original_completeness=meta.get('usage_completeness'),billing_complete=complete,nonstream_flag_correction=corrected,why=reason,raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest() if raw.exists() else None,observed_estimated_cost_CNY=meta.get('estimated_cost_CNY'),recomputed_cost_CNY=cost))
 record=dict(source_result_sha256=source_hash,raw_signature=raw_signature,evidence=str(run.relative_to(R)),missing_response_count=max(0,result.get('model_calls',0)-len(calls)),original_cost_incomplete=result.get('cost_incomplete'),cost_incomplete_reconciled=not calls or len(calls)!=result.get('model_calls') or not all(x['billing_complete'] for x in calls),corrected_nonstream_calls=sum(x['nonstream_flag_correction'] for x in calls),cost_estimate_unchanged=result.get('cost_estimated_CNY'),calls=calls,method='Non-stream terminal detection correction only; raw receipts and original run records preserved. Truncated/missing-usage requests remain incomplete, never zero-filled.')
 save(run/'usage-reconciliation.json',record);return record

def main():
 records=[one(p.parent) for p in sorted((R/'runs/formal').glob('*/*/result.json'))];save(R/'results/usage-reconciliation.json',records);print('Usage receipt audit',len(records),'runs,',sum(r['corrected_nonstream_calls'] for r in records),'non-stream flags corrected,',sum(r['cost_incomplete_reconciled'] for r in records),'still incomplete')
if __name__=='__main__':main()
