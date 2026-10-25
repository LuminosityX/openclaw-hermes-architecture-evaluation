"""Decompose real run timing/usage using observed API intervals, with overlap counted once."""
import datetime as dt,json,statistics
from pathlib import Path
from runtime import R,save

def one(run):
 rec=json.loads((run/'result.json').read_text());start=dt.datetime.fromisoformat(rec['started']).timestamp();end=start+rec['elapsed_seconds'];responses=rec.get('responses',[]);intervals=[]
 for response in responses:
  if response.get('at_utc') and isinstance(response.get('duration_seconds'),(int,float)):
   until=dt.datetime.fromisoformat(response['at_utc']).timestamp();begin=until-response['duration_seconds'];begin=max(start,begin);until=min(end,until)
   if until>begin:intervals.append((begin,until))
 intervals.sort();merged=[]
 for a,b in intervals:
  if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
  else:merged.append((a,b))
 wait=sum(b-a for a,b in merged);usage=[x.get('usage',{}) for x in responses];totals={k:sum(x.get(k,0) or 0 for x in usage) for k in ['prompt_tokens','completion_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens']}
 first=None
 for path in sorted(run.glob('api-request-*.json')):
  body=json.loads(path.read_text())
  if body.get('tools'):
   first=dict(call=int(path.stem.split('-')[-1]),tool_count=len(body['tools']),tool_definition_chars=len(json.dumps(body['tools'],ensure_ascii=False)),system_chars=sum(len(str(m.get('content',''))) for m in body.get('messages',[]) if m.get('role') in ['system','developer']),all_message_chars=len(json.dumps(body.get('messages',[]),ensure_ascii=False)));break
 return dict(task=rec['task'],variant=rec['variant'],repeat=rec['repeat'],family=rec['family'],passed=rec['passed'],elapsed_seconds=rec['elapsed_seconds'],observed_api_interval_union_seconds=wait,residual_wall_seconds=max(0,rec['elapsed_seconds']-wait),usage=totals,first_main_request_surface=first,evidence=str(run.relative_to(R)),limits='Residual includes framework preparation, actual tools, local task computation, scheduling, retry delays and evaluator process cleanup; it is not pure framework CPU. Union covers observed complete API handlers and clips to measured task time; failures/unknown usage remain flagged in primary results.')
def main():
 results=[one(p.parent) for p in sorted((R/'runs/formal').glob('*/*/result.json'))];save(R/'results/api-timing-and-usage.json',results);print('Analyzed',len(results),'completed real runs')
if __name__=='__main__':main()
