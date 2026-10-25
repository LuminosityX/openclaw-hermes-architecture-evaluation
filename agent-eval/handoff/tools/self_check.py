#!/usr/bin/env python3
"""Verify evaluator plumbing with known fixtures, not agents or API calls."""
import csv, importlib.util, json, shutil, subprocess, sys, tempfile, threading, urllib.request
from pathlib import Path
from prepare_run import prepare
from evaluate import evaluate
from effect_server import make_server
from score_pairs import score

ROOT=Path(__file__).resolve().parents[1]
def run_checks():
    checks=[]
    cfg=json.loads((ROOT/'experiment.json').read_text())
    assert cfg['families']['codex']['model']=='gpt-6.1-sol'
    assert all(cfg['families'][x]['model']=='deepseek-flash' for x in ['openclaw','hermes','dsh'])
    with tempfile.TemporaryDirectory(prefix='agent-eval-selfcheck-') as temp:
        blank=score(ROOT/'records/pairwise.csv')
        assert len(blank)==44 and all(x['grade'] is None for x in blank)
        with (ROOT/'records/pairwise.csv').open(newline='') as f:
            reader=csv.DictReader(f);headers=reader.fieldnames;example=list(reader)
        for row in example:
            row.update(decision='A优',evidence='synthetic_selfcheck_only',reviewer='selfcheck')
        pair_path=Path(temp)/'synthetic_pairs.csv'
        with pair_path.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=headers);writer.writeheader();writer.writerows(example)
        ranked=score(pair_path)
        assert [x['grade'] for x in ranked[:4]]==['强','中','中','弱']
        checks.append('scoring: missing evidence leaves grades empty; synthetic complete pairs calculate correctly')
        for variant in ['v1','v2','v3']:
            for task in ['W1','W2']:
                run=prepare('codex',task,variant,1,'selfcheck',temp)
                before,_=evaluate(run);assert before['passed'] is False,(task,variant,'baseline should fail')
                private=ROOT/'evaluator_private'/task/variant
                if task=='W1':shutil.copyfile(private/'reference.py',run/'workspace/pagination.py')
                else:
                    shutil.copyfile(private/'reference_model.py',run/'workspace/queueboard/model.py')
                    shutil.copyfile(private/'reference_service.py',run/'workspace/queueboard/service.py')
                # Avoid stale bytecode when fixture writes have equal-second mtimes.
                for cache in (run/'workspace').rglob('__pycache__'):shutil.rmtree(cache)
                after,_=evaluate(run);assert after['passed'] is True,(task,variant,after)
                checks.append(f'{task}/{variant}: baseline fails; reference passes')
            run=prepare('hermes','W3',variant,1,'selfcheck',temp)
            expected=json.loads((ROOT/'evaluator_private/W3'/variant/'expected.json').read_text())
            out=run/'workspace/output';out.mkdir()
            (out/'summary.json').write_text(json.dumps(expected['summary']))
            with (out/'clean.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=expected['columns']);w.writeheader();w.writerows(expected['clean'])
            result,_=evaluate(run);assert result['passed'] is True
            expected['summary']['kept_rows']+=1;(out/'summary.json').write_text(json.dumps(expected['summary']))
            result,_=evaluate(run);assert result['passed'] is False
            checks.append(f'W3/{variant}: golden passes; corrupted summary fails')
            run=prepare('dsh','W4',variant,1,'selfcheck',temp);result,_=evaluate(run)
            assert result['passed'] is None and result['manual_review_required']
        for task in ['W5','W6']:
            run=prepare('openclaw',task,'v1',1,'selfcheck',temp);result,_=evaluate(run)
            assert result['passed'] is None and result['manual_review_required']
            if task=='W6':
                completed=subprocess.run([sys.executable,'long_job.py','--run-id','selfcheck-job','--steps','1','--delay','0'],cwd=run/'workspace',capture_output=True,text=True,timeout=5)
                assert completed.returncode==0,completed.stderr
                events=[json.loads(x) for x in (run/'workspace/job_output/selfcheck-job.jsonl').read_text().splitlines()]
                assert len(events)==2 and events[-1]['completed'] is True
                checks.append('W6: bounded local job fixture writes valid step and completion events')
        server=make_server(Path(temp)/'server');thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_address[1]}'
        try:
            for drop in [False,True]:
                req=urllib.request.Request(base+'/effect',data=json.dumps({'operation_id':'same-op','drop_response':drop}).encode(),headers={'Content-Type':'application/json'})
                disconnected=False
                try:
                    with urllib.request.urlopen(req,timeout=3) as res:res.read()
                except Exception:
                    if not drop:raise
                    disconnected=True
                assert disconnected==drop,'drop-response behavior differs from fixture contract'
            with urllib.request.urlopen(base+'/state',timeout=3) as res:state=json.load(res)
            assert state['count']==2 and state['events'][0]['operation_id']==state['events'][1]['operation_id']
            checks.append('effect fixture: commit-before-drop; no automatic dedup')
        finally:server.shutdown();server.server_close();thread.join(timeout=3)
    return {'status':'passed','scope':'offline_fixture_and_harness_checks_only','model_calls':0,'product_runs':0,'checks':checks,'manual_tasks':'W4 semantic review and W5/W6 remain manual'}

if __name__=='__main__':print(json.dumps(run_checks(),ensure_ascii=False,indent=2))
