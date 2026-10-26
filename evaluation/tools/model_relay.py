"""Host-only DeepSeek credentials with a fixed-origin Unix-socket completion relay.

Agent namespaces receive only the socket, never the key or a writable host path.
The ledger contains usage/provenance, not prompts, responses or reasoning text.
"""
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
import re
import socketserver
import threading
import time
import urllib.error
import urllib.request

from provider_connection import NoRedirect

MAX_BODY=8*1024**2
MAX_RESPONSE=8*1024**2
TASK_PATTERN=re.compile(r'EVAL_[A-Z0-9_-]{1,90}')


def request_body(data,max_output_tokens=4096):
    if not isinstance(data,dict) or not isinstance(data.get('messages'),list):
        raise ValueError('Expected chat messages')
    # Retain the native protocol payload; replace only declared provider settings.
    body=dict(data,model='deepseek-flash',max_tokens=max_output_tokens,thinking={'type':'disabled'})
    body.pop('max_completion_tokens',None)
    if body.get('stream'):
        body['stream_options']={'include_usage':True}
    return body


def task_id(body):
    users=[str(row.get('content','')) for row in body.get('messages',[]) if row.get('role')=='user']
    for text in reversed(users):
        found=TASK_PATTERN.search(text)
        if found: return found.group()
    return None


class Metadata:
    """Parse completion metadata without retaining generated content."""
    def __init__(self,stream):
        self.stream=stream
        self.pending=b''
        self.usage=None
        self.model=None
        self.response_id=None
        self.finish_reasons=[]
        self.done=False
        self.response_bytes=0
        self.first_chunk_ns=None

    def consume(self,chunk):
        if self.first_chunk_ns is None: self.first_chunk_ns=time.monotonic_ns()
        self.response_bytes+=len(chunk)
        if self.response_bytes>MAX_RESPONSE: raise ValueError('Provider response exceeded finite protocol byte limit')
        self.pending+=chunk
        if self.stream:
            while b'\n' in self.pending:
                line,self.pending=self.pending.split(b'\n',1)
                if line.startswith(b'data:'):
                    payload=line[5:].strip()
                    if payload==b'[DONE]': self.done=True
                    elif payload:
                        try: self.object(json.loads(payload))
                        except (ValueError,TypeError): pass

    def object(self,data):
        if not isinstance(data,dict): return
        if isinstance(data.get('id'),str): self.response_id=data['id'][:200]
        if isinstance(data.get('model'),str): self.model=data['model'][:200]
        if isinstance(data.get('usage'),dict):
            # Only numerical token/charge metadata, never arbitrary provider fields.
            def counts(value):
                return {str(k)[:100]:(counts(v) if isinstance(v,dict) else v)
                        for k,v in value.items() if isinstance(v,(dict,int,float)) and not isinstance(v,bool)}
            self.usage=counts(data['usage'])
        for choice in data.get('choices',[]):
            reason=choice.get('finish_reason')
            if reason in {'stop','length','tool_calls','content_filter','insufficient_system_resource'}:
                if reason not in self.finish_reasons: self.finish_reasons.append(reason)

    def finish(self):
        if not self.stream:
            try: self.object(json.loads(self.pending))
            except (ValueError,TypeError): return
            self.done=True
        self.pending=b''


class Relay(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True
    block_on_close=False

    def __init__(self,path,key,max_output_tokens=4096,open_request=None):
        if not key: raise ValueError('DeepSeek key is required')
        self.key=key
        self.max_output_tokens=max_output_tokens
        self.open_request=open_request or urllib.request.build_opener(NoRedirect()).open
        self.records=[]
        self.lock=threading.Lock()
        self.path=Path(path)
        super().__init__(str(path),self.handler())
        self.path.chmod(0o600)

    def append(self,record):
        with self.lock: self.records.append(record)

    def handler(self):
        owner=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.0'
            def log_message(self,*args): pass

            def error(self,code,message):
                payload=json.dumps({'error':{'message':message,'type':'evaluation_relay_error'}}).encode()
                self.send_response(code)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self):
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=MAX_BODY: raise ValueError('Finite request byte limit exceeded')
                    raw=self.rfile.read(size)
                    if len(raw)!=size: raise ValueError('Incomplete local request')
                    if self.path!='/v1/chat/completions': return self.error(404,'Only the fixed completion endpoint is exposed')
                    body=request_body(json.loads(raw),owner.max_output_tokens)
                except (ValueError,TypeError): return self.error(400,'Invalid bounded completion request')
                raw=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
                record=dict(task_id=task_id(body),request_sha256=hashlib.sha256(raw).hexdigest(),
                            started_at_utc=datetime.now(timezone.utc).isoformat(),request_bytes=len(raw),
                            requested_model='deepseek-flash',thinking='disabled',max_output_tokens=owner.max_output_tokens,
                            stream=bool(body.get('stream')),upstream_status=None,usage=None,
                            provider_reported_cost_usd=None,invoice_reconciliation=None)
                started=time.monotonic_ns()
                metadata=Metadata(record['stream'])
                headers_sent=False
                request=urllib.request.Request('https://api.deepseek.com/chat/completions',data=raw,
                            headers={'Authorization':'Bearer '+owner.key,'Content-Type':'application/json','Accept':'application/json'})
                try:
                    with owner.open_request(request,timeout=120) as response:
                        record['upstream_status']=response.status
                        record['upstream_request_id']=response.headers.get('x-request-id','')[:200] or None
                        self.send_response(response.status)
                        self.send_header('Content-Type','text/event-stream' if metadata.stream else 'application/json')
                        self.end_headers()
                        headers_sent=True
                        while True:
                            chunk=response.read1(8192)
                            if not chunk: break
                            metadata.consume(chunk)
                            self.wfile.write(chunk)
                            self.wfile.flush()
                        metadata.finish()
                except urllib.error.HTTPError as error:
                    record['upstream_status']=error.code
                    record['error_type']='upstream-http-error'
                    if not headers_sent: self.error(error.code,'DeepSeek rejected the request; response body excluded from logs')
                except (OSError,ValueError,urllib.error.URLError) as error:
                    record['error_type']=type(error).__name__
                    if not headers_sent:
                        try: self.error(502,'Completion transport failed')
                        except OSError: pass
                finally:
                    record.update(duration_ms=(time.monotonic_ns()-started)/1e6,
                                  first_chunk_ms=None if metadata.first_chunk_ns is None else (metadata.first_chunk_ns-started)/1e6,
                                  response_bytes=metadata.response_bytes,response_id=metadata.response_id,
                                  response_model=metadata.model,usage=metadata.usage,finish_reasons=metadata.finish_reasons,
                                  stream_finished=metadata.done,usage_complete=metadata.usage is not None)
                    owner.append(record)
        return Handler

    def write_ledger(self,path):
        with self.lock: records=list(self.records)
        Path(path).write_text(json.dumps(dict(kind='real-provider-request-ledger',provider='deepseek',
            base_url='https://api.deepseek.com',model='deepseek-flash',campaign_spend_ceiling=None,
            requests=records,request_count=len(records),unattributed_request_count=sum(r['task_id'] is None for r in records),
            raw_prompts_retained=False,raw_responses_retained=False,credentials_retained=False,
            actual_charges_known=False,limitation='Usage metadata is not a provider invoice. Missing usage remains unknown.'),
            ensure_ascii=False,indent=2)+'\n')

    def server_close(self):
        super().server_close()
        self.key=''
        self.path.unlink(missing_ok=True)
