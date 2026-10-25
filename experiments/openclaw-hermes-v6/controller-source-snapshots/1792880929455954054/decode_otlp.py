"""Trusted post-run OTLP decoder; no agent or inference calls."""
import gzip,json
from pathlib import Path
from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
root=Path('/frames');records=[]
for meta in sorted(root.glob('*.json')):
 d=json.loads(meta.read_text());p=root/d['body_file'];body=p.read_bytes()
 if d.get('content_encoding')=='gzip':body=gzip.decompress(body)
 cls=ExportTraceServiceRequest if d['path'].endswith('/traces') else ExportMetricsServiceRequest if d['path'].endswith('/metrics') else ExportLogsServiceRequest
 try:msg=cls();msg.ParseFromString(body);d['decoded']=MessageToDict(msg,preserving_proto_field_name=True)
 except Exception as ex:d['decode_error']=type(ex).__name__
 records.append(d)
Path('/workspace/otlp-decoded.json').write_text(json.dumps(records,ensure_ascii=False,indent=2));print(json.dumps({'frames':len(records),'decoded':sum('decoded' in x for x in records)}))
