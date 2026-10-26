"""Paired native baseline/reuse tasks; learned AGENTS is produced by the agent."""
import hashlib
import json
from pathlib import Path
import time

from conversation_cases import turn
import pilot
import task_cases


def configure(root,task,thinking):
    config=task_cases.configure(root,task,thinking)
    config['tools']['allow'].append('write');config['tools']['fs']=dict(workspaceOnly=True)
    config['agents']['defaults']['compaction']=dict(enabled=False,memoryFlush=dict(enabled=False))
    pilot.save(root/'config.json',config);return config


def execute(root,task,thinking,report,fixture):
    root.mkdir(parents=True,exist_ok=True);series={};integrity={name:True for name in task['files']};resources=[];started=time.monotonic_ns();gateway=None
    original_task=fixture.task
    try:
        for arm in task['reuse']['arm_order']:
            directory=root/arm;arm_task=dict(task,artifact='answer.json');fixture.task_root=directory;fixture.task=arm_task
            gateway=pilot.Gateway(directory,configurer=lambda p:configure(p,arm_task,thinking));gateway.ready()
            record=dict(answers=[],asset_created=False,asset_marker_present=False)
            if arm=='reuse':
                prompt='COST_STAGE_LEARN '+task['task_id']+'\n'+task['reuse']['learning_prompt']
                record['learning']=turn(gateway,'agent:main:eval:'+task['task_id'].lower()+':learning',prompt,task['reuse']['learning_timeout_seconds'])
                asset=directory/'workspace/AGENTS.md'
                if asset.is_file() and not asset.is_symlink() and asset.stat().st_size<=16384:
                    data=asset.read_bytes();record.update(asset_created=True,asset_marker_present=task['reuse']['asset_marker'].encode() in data,
                        asset_bytes=len(data),asset_sha256=hashlib.sha256(data).hexdigest(),asset_text=data.decode(errors='replace'))
            for index,item in enumerate(task['reuse']['orders']):
                artifact_name=f'answer-{arm}-{index:02}.json';arm_task['artifact']=artifact_name
                artifact=directory/'workspace'/artifact_name;artifact.unlink(missing_ok=True)
                version=item['policy_version'];order=item['order']
                prompt=('COST_STAGE_'+arm.upper()+'_TASK_'+str(index)+' '+task['task_id']+'\n'
                    f'Active policy version is {version}. Solve this order: '+json.dumps(order)+'. '
                    f'Use rulebook-v{version}.txt as needed; a reusable guide is valid only if its version matches. '
                    f'Write {artifact_name} with exactly order_id, policy_version (integer) and credits (integer). Do not change reference files.')
                session='agent:main:eval:'+task['task_id'].lower()+':'+arm+':'+str(index)
                result=turn(gateway,session,prompt,task['reuse']['later_task_timeout_seconds'])
                text=artifact.read_text() if artifact.is_file() and not artifact.is_symlink() and artifact.stat().st_size<=8192 else None
                record['answers'].append(dict(index=index,**result,artifact_text=text,artifact_sha256=hashlib.sha256(text.encode()).hexdigest() if text is not None else None))
            record['resources']=gateway.sampler.summary();resources.append(record['resources']);gateway.stop();gateway=None
            for name,content in task['files'].items():
                path=directory/'workspace'/name;integrity[name]=integrity[name] and path.is_file() and not path.is_symlink() and path.read_text()==content
            series[arm]=record
        statuses=[r['status'] for arm in series.values() for r in arm['answers']]+[series['reuse'].get('learning',{}).get('status')]
        all_completed=all(status==200 for status in statuses)
        report.update(artifacts={'series.json':json.dumps(series,ensure_ascii=False,separators=(',',':'))},input_integrity=integrity,
            native_http_status=200 if all_completed else None,completion_ms=(time.monotonic_ns()-started)/1e6,reuse_sequence_exercised=True,
            reuse_profile=dict(horizon=task['reuse']['horizon'],arm_order=task['reuse']['arm_order'],
                native_asset='Agent-written root AGENTS.md; separate native state/workspace per arm; fresh native session per delivery',
                accepted_delivery_count_computed_on_host=True,actual_invoice_cost_known=False,
                endpoint_status_scope='Compound experiment: all recorded per-turn native HTTP responses must be 200; each delivery is independently scored on the host.'),arm_resources=resources)
        if not all_completed:report['task_transport_error']='OneOrMoreSequenceEndpointsFailed'
    finally:
        fixture.task=original_task
        if gateway:gateway.stop();report['native_gateway_tail']=''.join(gateway.log_tail)[-3000:]
