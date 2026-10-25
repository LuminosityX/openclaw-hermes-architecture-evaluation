"""Run a small, independently checked paired DeepSeek task after private key setup."""
import json
import subprocess
import sys
import time
from pathlib import Path
from configure_deepseek import configured_key
from run_initial import ROOT,NODE,TSX,PYTHON,ENV

def main():
    key=configured_key()
    if not key:
        print(json.dumps({'status':'needs_private_key','api_calls':0,'next_step':'Run scripts/configure_deepseek.py in an interactive terminal'}))
        return 2
    spec=json.loads((ROOT/'results/real-pilot-spec.json').read_text())
    records=[]
    for framework in ['hermes','openclaw']:
        run_id=f'{framework}-deepseek-pilot-{time.time_ns()}'
        workspace=ROOT/f'fixtures/real-pilot/{framework}/csv-aggregation'
        output=ROOT/f'raw/{run_id}.json'
        result_file=workspace/'result.json'
        if result_file.exists():
            result_file.rename(workspace/f'result-before-{run_id}.json')
        env=dict(ENV)
        # Pass only to this task-owned child, never to command arguments or persisted config.
        env['DEEPSEEK_API_KEY']=key
        if framework=='hermes':
            command=[str(PYTHON),str(ROOT/'scripts/hermes_deepseek_case.py'),'--prompt-file',str(workspace/'task.txt'),'--run-id',run_id,'--output',str(output),'--cwd',str(workspace),'--max-iterations','6','--max-tokens','4096']
            cwd=ROOT
        else:
            env.update({'BENCH_CONFIG_PATH':str(ROOT/'envs/openclaw-deepseek-config.json'),'BENCH_MODEL':'deepseek-bench/deepseek-flash','BENCH_PROMPT_FILE':str(workspace/'task.txt'),'BENCH_RUN_ID':run_id,'BENCH_WORKSPACE':str(workspace),'BENCH_STATE_DIR':str(ROOT/'runtime/real-openclaw'/run_id),'BENCH_OUTPUT':str(output),'BENCH_TIMEOUT':'180','BENCH_SAMPLES':'1','BENCH_WARMUPS':'0'})
            command=[str(NODE),'--import',str(TSX),str(ROOT/'scripts/openclaw_agent_probe.mjs'),'real','0','0','terminal']
            cwd=ROOT/'sources/openclaw'
        started=time.monotonic()
        process=subprocess.Popen(command,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        try:
            stdout,stderr=process.communicate(timeout=240)
        except subprocess.TimeoutExpired:
            import os,signal
            os.killpg(process.pid,signal.SIGTERM)
            try:stdout,stderr=process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);stdout,stderr=process.communicate()
        elapsed=time.monotonic()-started
        # Defensive redaction even if a third-party SDK includes credentials in an error.
        stdout=stdout.replace(key,'[REDACTED]');stderr=stderr.replace(key,'[REDACTED]')
        (ROOT/f'logs/{run_id}.stdout.log').write_text(stdout)
        (ROOT/f'logs/{run_id}.stderr.log').write_text(stderr)
        actual=None;parse_error=None
        if result_file.exists():
            try:actual=json.loads(result_file.read_text())
            except (ValueError,OSError) as error:parse_error=type(error).__name__
        correct=actual==spec['expected']
        record={'framework':framework,'case_id':spec['case_id'],'run_id':run_id,'model':'deepseek-flash','base_url':'https://api.deepseek.com','thinking':'disabled','temperature':0,'max_tokens':4096,'process_wall_seconds':elapsed,'process_exit_code':process.returncode,'result_file_exists':result_file.exists(),'correct':correct,'parse_error':parse_error,'actual':actual,'native_result':str(output.relative_to(ROOT)) if output.exists() else None,'cost_known':False,'cost_note':'Record native token usage; zero/default framework prices must not be interpreted as actual billed cost.'}
        records.append(record)
        (ROOT/'results/real-pilot-results.json').write_text(json.dumps({'status':'pilot_measured','scope':'One CSV task per framework; correctness checked by exact generated-file equality. Wall time includes source initialization; insufficient for task success-rate or resource-efficiency ranking.','records':records},ensure_ascii=False,indent=2))
        print(json.dumps({k:record[k] for k in ['framework','run_id','correct','process_exit_code','process_wall_seconds']},ensure_ascii=False),flush=True)
    return 0 if all(r['correct'] for r in records) else 1

if __name__=='__main__':raise SystemExit(main())
