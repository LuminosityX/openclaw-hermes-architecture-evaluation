"""Read only the final current tool result of each actual release phase."""
import hashlib,json
from runtime import R,save
from run_state_ops import disabled_job_in

def main():
 rows=[]
 for p in sorted((R/'runs-upgrades').glob('u*/*/*/*/controlled-requests.json')):
  calls=json.loads(p.read_text());last=next((x['request'] for x in reversed(calls) if x['main']),{});tools=[m for m in last.get('messages',[]) if m.get('role')=='tool'];value=tools[-1].get('content') if tools else None
  rows.append(dict(path=str(p.relative_to(R)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),last_current_tool_is_disabled_job=disabled_job_in(value),tail_tool_sha256=hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()))
 if len(rows)!=18:raise RuntimeError('Expected old/new/rollback for six profiles, not '+str(len(rows)))
 save(R/'results/upgrade-current-job-audit.json',dict(phases=rows,passed=all(x['last_current_tool_is_disabled_job'] for x in rows),scope='Posthoc original native wire records, last current tool only. Stronger later controller code is not claimed to have executed in cached earlier phases.'))
 print('CURRENT_PHASE_DISABLED_JOBS',sum(x['last_current_tool_is_disabled_job'] for x in rows),len(rows))
if __name__=='__main__':main()
