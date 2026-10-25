"""Read official closed ATIF observations and accepted OTLP exports only.
Run with the already-pinned evaluator decoder venv, not a product dependency.
"""
import gzip,hashlib,json
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

R=Path('/root/output/oc-hermes-execution-20261024-v6')

def attributes(span):return {z['key']:next(iter(z['value'].values())) for z in span.get('attributes',[])}

def main():
    cases=json.loads((R/'results/session-closure.json').read_text())
    if len(cases)!=6:raise RuntimeError('Closure guards incomplete')
    result=[]
    for row in cases:
        run=R/'runs-observability-closure'/row['mode']/f"u{row['unit']}"/'hermes';native=[];ids=set();shas=[]
        for item in row['atif_files_after_second_turn']:
            file=R/item['path'];raw=file.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise RuntimeError('Native ATIF evidence hash changed')
            x=json.loads(raw);shas.append(item['sha256'])
            for step in x['steps']:
                for index,z in enumerate(step.get('observation',{}).get('results',[])):
                    if z.get('extra',{}).get('event_name')!='terminal':continue
                    identity=z.get('source_call_id') or z.get('extra',{}).get('metadata',{}).get('tool_call_id')
                    if identity not in ['controlled-0-0','controlled-1-0','controlled-2-0']:continue
                    value=json.loads(z['content'])
                    if identity=='controlled-2-0':ok=value.get('status')=='blocked' and value.get('exit_code')==-1 and 'Command denied by user' in value.get('error','')
                    else:ok=value.get('output','').strip()==('NATIVE_RESULT_first' if identity=='controlled-0-0' else 'NATIVE_RESULT_second') and value.get('exit_code')==0
                    if ok:ids.add(identity)
                    native.append(dict(file=item['path'],step_id=step['step_id'],observation_index=index,source_call_id=identity,correct_result=ok,task_id=z['extra'].get('metadata',{}).get('task_id'),event_uuid=z['extra'].get('event_uuid')))
        received=set();span_count=0;rejected=0;decode_errors=[]
        for meta in (run/'otlp-frames').glob('*.json'):
            m=json.loads(meta.read_text())
            if not m['path'].endswith('/traces'):continue
            if not m['accepted']:rejected+=1;continue
            body=(meta.parent/m['body_file']).read_bytes()
            if m.get('content_encoding')=='gzip':body=gzip.decompress(body)
            try:p=ExportTraceServiceRequest();p.ParseFromString(body);d=MessageToDict(p,preserving_proto_field_name=True)
            except Exception as e:decode_errors.append(type(e).__name__);continue
            for resource in d.get('resource_spans',[]):
                for scope in resource.get('scope_spans',[]):
                    for span in scope.get('spans',[]):
                        span_count+=1
                        if span['name']=='terminal':
                            ident=attributes(span).get('nemo_relay.tool_call_id')
                            if ident:received.add(ident)
        result.append(dict(unit=row['unit'],mode=row['mode'],same_native_session=row['same_native_session'],both_turns_completed=row['first_task_completed'] and row['second_turn_completed'],atif_absent_before_segment_close=row['atif_files_before_second_turn']==0,atif_complete_tool_outputs=ids=={'controlled-0-0','controlled-1-0','controlled-2-0'},native_atif_observations=native,atif_sha256=shas,accepted_remote_tool_ids=sorted(received),accepted_remote_span_count=span_count,rejected_trace_frames=rejected,decode_errors=decode_errors))
    path=R/'results/session-closure-native-audit.json';path.write_text(json.dumps(dict(rows=result,scope='Actual official native ATIF output fields tied to native tool call IDs, after a documented same-session segment closure. Request/command strings and external truth records are not accepted as tool-output retention. This finite guard does not certify long-term retention or every OTLP retry policy.'),ensure_ascii=False,indent=2))
    print('CLOSED_NATIVE_TRAJECTORY_AUDIT',[(x['mode'],x['unit'],x['atif_complete_tool_outputs'],x['accepted_remote_tool_ids'],x['rejected_trace_frames']) for x in result],flush=True)

if __name__=='__main__':main()
