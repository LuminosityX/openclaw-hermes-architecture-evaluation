"""Owned MCP Streamable HTTP and legacy SSE peers; no external destinations."""
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import queue
import socket
import threading
import time
from urllib.parse import parse_qs,urlsplit
import uuid


def content_result(token,format='text'):
    receipt='RECEIPT:'+token
    result=dict(content=[dict(type='text',text=receipt)],isError=False)
    if format=='structured':result['structuredContent']=dict(receipt=receipt,marker='STRUCTURED_ONLY_'+token,value=17)
    if format=='resource':result['content'].append(dict(type='resource',resource=dict(uri='eval-fixture://owned/'+token,mimeType='text/plain',text='RESOURCE_BODY_'+token)))
    if format=='unicode':result['content'].append(dict(type='text',text='Unicode_π_中文_🙂_\nEND_'+token))
    if format=='large':result['content'].append(dict(type='text',text='LARGE_BEGIN_'+token+'\n'+'q'*(32*1024)+'\nLARGE_END_'+token))
    return result


class McpHTTPFixture:
    def __init__(self,transport='streamable-http',port=18085,tls_context=None,bind_host='127.0.0.1',gate_timeout_seconds=15):
        if type(gate_timeout_seconds) is not int or not 1<=gate_timeout_seconds<=600:raise ValueError('Owned MCP gate requires a finite 1..600 second limit')
        self.gate_timeout_seconds=gate_timeout_seconds
        self.transport=transport;self.events=[];self.sessions={};self.tasks={};self.calls={};self.receipts={}
        self.lock=threading.Lock();self.stop=threading.Event();self.release=threading.Event();self.release.set()
        self.expire_on_tokens=set()
        self.server=ThreadingHTTPServer((bind_host,port),self.handler());self.server.daemon_threads=True
        if tls_context is not None:self.server.socket=tls_context.wrap_socket(self.server.socket,server_side=True)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()

    def event(self,kind,**values):
        with self.lock:self.events.append(dict(kind=kind,monotonic_ns=time.monotonic_ns(),**values))

    def register(self,token,**options):
        self.tasks[token]={'format':'text','gate':False,'commit_before_gate':False,'drop_after_commit':False,'ignore_cancel':False,**options}

    def session(self):
        identifier=uuid.uuid4().hex
        with self.lock:
            self.sessions[identifier]=dict(generation=len(self.sessions)+1,valid=True,queue=queue.Queue())
        self.event('mcp-session-created',generation=self.sessions[identifier]['generation'])
        return identifier

    def expire(self):
        for session in self.sessions.values():session['valid']=False
        self.event('mcp-sessions-expired')

    def response(self,body,session_id):
        method=body.get('method');identifier=body.get('id');params=body.get('params',{})
        generation=self.sessions.get(session_id,{}).get('generation')
        self.event('mcp-request',method=method,generation=generation,request_id=str(identifier) if identifier is not None else None)
        if method=='notifications/cancelled':
            call=self.calls.get((session_id,str(params.get('requestId'))))
            if call:call.set()
            self.event('mcp-cancel-notification',generation=generation,request_id=str(params.get('requestId')),matched=call is not None)
            return None
        if identifier is None:return None
        result={}
        if method=='initialize':
            result=dict(protocolVersion=params.get('protocolVersion','2025-03-26'),capabilities=dict(tools=dict(listChanged=False)),serverInfo=dict(name='owned-http-probe',version='1.0.0'))
        elif method=='tools/list':
            result=dict(tools=[dict(name='eval_probe',description='Owned independently receipted MCP contract operation',inputSchema=dict(type='object',
                properties=dict(token=dict(type='string'),action=dict(type='string'),unicode=dict(type='string')),required=['token']))])
        elif method=='tools/call':
            args=params.get('arguments',{});token=args.get('token');task=self.tasks.get(token)
            if task is None:return dict(jsonrpc='2.0',id=identifier,error=dict(code=-32602,message='Unknown owned task'))
            cancel=threading.Event();self.calls[(session_id,str(identifier))]=cancel
            self.event('mcp-tool-start',token=token,generation=generation,arguments=args)
            def commit():
                with self.lock:self.receipts[token]=self.receipts.get(token,0)+1;ordinal=self.receipts[token]
                self.event('mcp-effect-commit',token=token,generation=generation,ordinal=ordinal)
            try:
                if task['commit_before_gate']:commit()
                if task['gate'] and not self.release.wait(timeout=self.gate_timeout_seconds):
                    self.event('mcp-fixture-gate-timeout',token=token)
                    return dict(jsonrpc='2.0',id=identifier,error=dict(code=-32001,message='Owned fixture gate timed out'))
                if cancel.is_set() and not task['ignore_cancel']:
                    self.event('mcp-cooperative-cancel',token=token)
                    return dict(jsonrpc='2.0',id=identifier,error=dict(code=-32800,message='Owned operation cancelled'))
                if not task['commit_before_gate']:commit()
                result=content_result(token,task['format'])
                self.event('mcp-tool-return-attempt',token=token,generation=generation,cancelled=cancel.is_set(),
                    bytes=len(json.dumps(result).encode()),result_sha256=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest())
                if task['drop_after_commit']:
                    self.sessions[session_id]['valid']=False
                    return dict(_drop_connection=True)
            finally:self.calls.pop((session_id,str(identifier)),None)
        elif method not in {'ping','logging/setLevel'}:
            return dict(jsonrpc='2.0',id=identifier,error=dict(code=-32601,message='Method not found'))
        return dict(jsonrpc='2.0',id=identifier,result=result)

    def handler(self):
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,status,data=None,session=None):
                raw=json.dumps(data).encode() if data is not None else b''
                self.send_response(status)
                if raw:self.send_header('Content-Type','application/json')
                if session:self.send_header('Mcp-Session-Id',session)
                self.send_header('Content-Length',str(len(raw)));self.end_headers()
                try:self.wfile.write(raw);self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):owner.event('mcp-response-lost')

            def do_GET(self):
                if self.path!='/sse' or owner.transport!='sse':return self.send(405)
                identifier=owner.session();session=owner.sessions[identifier]
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-cache');self.end_headers()
                try:
                    self.wfile.write(('event: endpoint\ndata: /messages?sessionId='+identifier+'\n\n').encode());self.wfile.flush()
                    while not owner.stop.is_set():
                        try:value=session['queue'].get(timeout=.5)
                        except queue.Empty:continue
                        self.wfile.write(('event: message\ndata: '+json.dumps(value)+'\n\n').encode());self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):owner.event('mcp-sse-peer-closed',generation=session['generation'])

            def do_DELETE(self):
                identifier=self.headers.get('Mcp-Session-Id')
                if identifier in owner.sessions:owner.sessions[identifier]['valid']=False
                return self.send(200)

            def do_POST(self):
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=1024**2:return self.send(413)
                body=json.loads(self.rfile.read(size));parsed=urlsplit(self.path)
                legacy=parsed.path=='/messages' and owner.transport=='sse'
                if legacy:identifier=parse_qs(parsed.query).get('sessionId',[None])[0]
                elif parsed.path=='/mcp' and owner.transport=='streamable-http':identifier=self.headers.get('Mcp-Session-Id')
                else:return self.send(404)
                if body.get('method')=='initialize' and not legacy:
                    identifier=owner.session()
                token=body.get('params',{}).get('arguments',{}).get('token')
                if body.get('method')=='tools/call' and token in owner.expire_on_tokens and identifier in owner.sessions:
                    owner.expire_on_tokens.remove(token);owner.sessions[identifier]['valid']=False
                    owner.event('mcp-live-session-expiry-injected',token=token,generation=owner.sessions[identifier]['generation'])
                if identifier not in owner.sessions or not owner.sessions[identifier]['valid']:
                    owner.event('mcp-session-rejected',method=body.get('method'),http_status=404)
                    return self.send(404,dict(error='Owned MCP session expired'))
                if legacy:
                    self.send(202)
                    value=owner.response(body,identifier)
                    if value is not None:owner.sessions[identifier]['queue'].put(value)
                    return
                value=owner.response(body,identifier)
                if value is None:return self.send(202)
                if value.get('_drop_connection'):
                    owner.event('mcp-connection-dropped-after-effect')
                    self.connection.shutdown(socket.SHUT_RDWR);self.connection.close();return
                return self.send(200,value,identifier if body.get('method')=='initialize' else None)
        return Handler

    def close(self):
        self.release.set();self.stop.set();self.server.shutdown();self.server.server_close()
