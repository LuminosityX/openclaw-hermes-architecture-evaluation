"""Native trace identity replay audit of same-tool-phase collector controls."""
import gzip,hashlib,json
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

R=Path('/root/output/oc-hermes-execution-20261024-v6')

def main():
    cases=json.loads((R/'results/matched-collector-outage.json').read_text())
    if len(cases)!=6:raise RuntimeError('Matched tool-phase cases incomplete')
    output=[]
    for row in cases:
        run=R/'runs-matched-collector-outage'/f"u{row['unit']}"/row['family'];records={True:[],False:[]};errors=[]
        for file in sorted((run/'otlp-frames').glob('*.json')):
            m=json.loads(file.read_text())
            if not m['path'].endswith('/traces'):continue
            body=(file.parent/m['body_file']).read_bytes()
            if m.get('content_encoding')=='gzip':body=gzip.decompress(body)
            try:p=ExportTraceServiceRequest();p.ParseFromString(body);d=MessageToDict(p,preserving_proto_field_name=True)
            except Exception as e:errors.append(type(e).__name__);continue
            for resource in d.get('resource_spans',[]):
                for scope in resource.get('scope_spans',[]):
                    for s in scope.get('spans',[]):
                        if s['name']!=('openclaw.tool.execution' if row['family']=='openclaw' else 'terminal'):continue
                        a={z['key']:next(iter(z['value'].values())) for z in s.get('attributes',[])}
                        identity=a.get('gen_ai.tool.call.id') or a.get('nemo_relay.tool_call_id')
                        if identity:records[m['accepted']].append(dict(call_id=identity,trace_id=s['trace_id'],span_id=s['span_id'],frame=str(file.relative_to(R)),frame_monotonic_ns=m['at_ns']))
        rejected={z['call_id'] for z in records[False]};accepted={z['call_id'] for z in records[True]}
        failed_first={(z['trace_id'],z['span_id']) for z in records[False] if z['call_id']=='controlled-0-0'}
        accepted_first={(z['trace_id'],z['span_id']) for z in records[True] if z['call_id']=='controlled-0-0'}
        local=[]
        if row['family']=='hermes':
            for file in (run/'state/hermes/telemetry/eval-atif').glob('*.json'):
                obj=json.loads(file.read_text())
                for step in obj['steps']:
                    for z in step.get('observation',{}).get('results',[]):
                        if z.get('extra',{}).get('event_name')!='terminal':continue
                        ident=z.get('source_call_id') or z['extra'].get('metadata',{}).get('tool_call_id')
                        if ident not in ['controlled-0-0','controlled-1-0','controlled-2-0']:continue
                        value=json.loads(z['content']);ok=(value.get('status')=='blocked' and 'Command denied by user' in value.get('error','')) if ident=='controlled-2-0' else value.get('output','').strip()==('NATIVE_RESULT_first' if ident=='controlled-0-0' else 'NATIVE_RESULT_second')
                        if ok:local.append(dict(file=str(file.relative_to(R)),call_id=ident,step_id=step['step_id'],event_uuid=z['extra']['event_uuid']))
        valid=bool(row['first_task_completed'] and row['actual_trace_rejection'] and failed_first and not errors)
        output.append(dict(unit=row['unit'],family=row['family'],valid_same_first_tool_rejection=valid,rejected_tool_ids=sorted(rejected),accepted_tool_ids=sorted(accepted),same_first_tool_span_replayed=bool(failed_first & accepted_first),native_rejected_records=records[False],native_accepted_records=records[True],local_atif_tool_outputs=local,local_atif_complete={z['call_id'] for z in local}=={'controlled-0-0','controlled-1-0','controlled-2-0'} if row['family']=='hermes' else None,healthy_observation_seconds=row['healthy_observation_seconds'],decode_errors=errors))
    result=dict(rows=output,scope='Same-original-unit controls, actual first tool span positively rejected in both products, five-second collector outage and twenty-second healthy window. An exact (trace_id, span_id) match proves automatic replay of the rejected span; a requested command or new unrelated span does not. Hermes local native ATIF recovery is separately counted. No claim about indefinite retry or all public exporter configurations.')
    (R/'results/matched-collector-native-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('MATCHED_TOOL_PHASE_NATIVE_AUDIT',[(z['unit'],z['family'],z['valid_same_first_tool_rejection'],z['same_first_tool_span_replayed'],z['local_atif_complete']) for z in output],flush=True)
    if not all(z['valid_same_first_tool_rejection'] for z in output):raise RuntimeError('No comparative retry conclusion from an invalid same-tool rejection')

if __name__=='__main__':main()
