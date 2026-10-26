"""Preregistered bounded long-history, native compaction and continuation tasks."""
import hashlib
import json


def workload(sid,unit):
    if sid not in {f'PERF-10-S{i:02}' for i in range(1,6)} or type(unit) is not int or not 1<=unit<=6:raise ValueError('Unknown conversation task/unit')
    number=int(sid[-2:]);task_id='EVAL_'+sid.replace('-','_')+'_U'+str(unit)
    anchor='MemoryAnchor'+hashlib.sha256(task_id.encode()).hexdigest()[:24]
    marker='REFERENCE_END_'+sid.replace('-','_')+'_U'+str(unit)
    expected=dict(release='2026-10',cache_ttl_seconds=19+unit,retention_days=7+unit,memory_anchor=anchor)
    facts={k:v for k,v in expected.items() if k!='memory_anchor'}
    source='Released configuration: '+json.dumps(facts)+'\n'
    primers=[]
    if number in {2,3,5}:
        count=4 if number==3 else 6;size=8192 if number==3 else 16384
        for i in range(count):
            filler=''.join(f'Background row {j:04}: synthetic context note {i}; no released configuration change.\n' for j in range(400))[:size]
            primers.append('PRIME_STAGE_'+str(i)+' '+task_id+'\n'+
                (('Remember the exact setup memory_anchor '+anchor+' for the later task.\n') if i==0 else '')+
                'This is background only. Acknowledge with ACK and do not use tools yet.\n'+filler)
    else:source+='Setup memory_anchor: '+anchor+'\n'
    if number==4:
        source=''.join(f'Irrelevant source row {i:04}; the released settings appear at the end.\n' for i in range(1500))[:65536]+source
    source+=marker+'\n'
    task=dict(schema_version=1,scenario_id=sid,unit=unit,task_id=task_id,provider='deepseek',model='deepseek-flash',
        files={'reference.txt':source},artifact='answer.json',timeout_seconds=180,whole_unit_timeout_seconds=900,
        maximum_model_requests=32,maximum_output_tokens_per_request=4096,
        prompt='Read reference.txt. Write answer.json with exactly release, cache_ttl_seconds, retention_days and memory_anchor. Use the latest released settings in the file and the exact setup memory_anchor from this conversation, or from the source when supplied there. Do not modify inputs. Preserve numeric JSON types.',
        oracle=dict(kind='json-artifact',expected=expected),
        conversation=dict(primers=primers,force_native_compaction=number==3,restart_before_final=number==5,
            anchor=anchor,source_marker=marker,source_bytes=len(source.encode()),context_window=131072))
    public=dict(task_id=task_id,prompt=task['prompt'],files=dict(task['files']),artifact=task['artifact'],conversation=task['conversation'],
        resource_limits={k:task[k] for k in ['timeout_seconds','maximum_model_requests','maximum_output_tokens_per_request']})
    task.update(public=public,public_fixture_sha256=hashlib.sha256(json.dumps(public,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
    return task
