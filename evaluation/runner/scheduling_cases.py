"""Native multi-call scheduling, with actual owned reads and connection receipts."""
import hashlib
import io
import json
import re
import shutil
import time

from mcp_http_fixture import McpHTTPFixture
from operation_fixture import OperationFixture
import pilot
import service_path_cases as service

SCENARIOS={f'PERF-03-S{i:02}':name for i,name in enumerate(['independent','chain','one-connection','two-connections'],1)}


class BatchFixture(OperationFixture):
    def __init__(self):
        self.batches={};self.batch_returns={}
        super().__init__()

    def batch(self,token,calls,chain=False):
        self.register(token);self.batches[token]=dict(calls=calls,chain=chain)

    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def do_POST(self):
                if not self.path.endswith('/chat/completions'):return super().do_POST()
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4*1024**2:return self.send(dict(error='fixture-bound'),413)
                raw=self.rfile.read(size);body=json.loads(raw)
                marked=[(i,re.search(r'PILOT_[A-Z0-9_]+',str(m.get('content','')))) for i,m in enumerate(body.get('messages',[])) if m.get('role')=='user']
                marked=[(i,m.group()) for i,m in marked if m]
                index,token=marked[-1] if marked else (0,None)
                if token not in owner.batches:
                    original=self.rfile;self.rfile=io.BytesIO(raw)
                    try:return super().do_POST()
                    finally:self.rfile=original
                plan=owner.batches[token];results=[m for m in body['messages'][index+1:] if m.get('role')=='tool']
                owner.batch_returns[token]=results
                text=json.dumps(results,ensure_ascii=False)
                done={i for i,c in enumerate(plan['calls']) if 'RECEIPT:'+c['arguments']['token'] in text}
                names=[t.get('function',{}).get('name') for t in body.get('tools',[])]
                owner.event('batch-provider-request',token=token,completed_calls=sorted(done),advertised_tools=names)
                if results and (len(done)==len(plan['calls']) or not plan['chain']):
                    message=dict(role='assistant',content=('ACCEPTED:' if len(done)==len(plan['calls']) else 'INCOMPLETE:')+token);finish='stop'
                else:
                    pending=[i for i in range(len(plan['calls'])) if i not in done]
                    if plan['chain']:pending=pending[:1]
                    calls=[]
                    for i in pending:
                        item=plan['calls'][i];tool=item['tool'];arguments=item['arguments']
                        if tool not in names and 'tool_call' in names:arguments=dict(id=tool,args=arguments);tool='tool_call'
                        calls.append(dict(id='batch_'+hashlib.sha256((token+str(i)).encode()).hexdigest()[:16],type='function',function=dict(name=tool,arguments=json.dumps(arguments))))
                    message=dict(role='assistant',content=None,tool_calls=calls);finish='tool_calls'
                common=dict(id='owned-batch',created=1760000000,model='fixture-model')
                if not body.get('stream'):return self.send(dict(**common,object='chat.completion',choices=[dict(index=0,message=message,finish_reason=finish)],usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0)))
                delta=dict(message)
                if 'tool_calls' in delta:delta['tool_calls']=[dict(index=i,**c) for i,c in enumerate(delta['tool_calls'])]
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                try:
                    for value,reason in [(delta,None),({},finish)]:self.wfile.write(('data: '+json.dumps(dict(**common,object='chat.completion.chunk',choices=[dict(index=0,delta=value,finish_reason=reason)]))+'\n\n').encode())
                    self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):owner.event('batch-provider-disconnected',token=token)
        return Handler


class ReadPeer(McpHTTPFixture):
    def __init__(self,root,port):
        self.root=root;self.active=0;self.peak_active=0
        super().__init__(port=port)

    def response(self,body,session_id):
        if body.get('method')=='tools/list':
            result=super().response(body,session_id)
            result['result']['tools'][0]['annotations']=dict(readOnlyHint=True,destructiveHint=False)
            return result
        if body.get('method')!='tools/call':return super().response(body,session_id)
        token=body.get('params',{}).get('arguments',{}).get('token')
        if token not in self.tasks:return super().response(body,session_id)
        with self.lock:self.active+=1;self.peak_active=max(self.peak_active,self.active)
        self.event('owned-read-start',token=token,port=self.server.server_address[1],generation=self.sessions[session_id]['generation'])
        try:
            path=self.root/(token+'.txt');value=path.read_text()
            time.sleep(.25)
            result=super().response(body,session_id)
            result['result']['content'].append(dict(type='text',text=value))
            self.event('owned-read-end',token=token,sha256=hashlib.sha256(value.encode()).hexdigest())
            return result
        finally:
            with self.lock:self.active-=1


def configure(root,two):
    config=service.configure(root);servers={}
    for i,port in enumerate([18085,18086] if two else [18085]):
        name='reads'+str(i)
        servers[name]=dict(transport='streamable-http',url=f'http://127.0.0.1:{port}/mcp',supportsParallelToolCalls=True,requestTimeoutMs=10000,connectionTimeoutMs=5000)
        config['tools']['allow'].append(name+'__eval_probe')
    config['mcp']=dict(servers=servers);pilot.save(root/'config.json',config);return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];fixture=BatchFixture();peers=[];gateway=None;assertions=[]
    token='PILOT_SCHEDULING_'+scenario.replace('-','_')+'_U'+str(unit)
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-batched-tool-results','independent-owned-read-events','connection-generations']))
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:configure(p,mode=='two-connections'))
        for port in ([18085,18086] if mode=='two-connections' else [18085]):peers.append(ReadPeer(root/'workspace',port))
        gateway.ready();control=token+'_CONTROL';fixture.register(control)
        if not gateway.request(control)['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Native provider/effect control failed')
        for i,peer in enumerate(peers):
            c=token+'_PEER_CONTROL_'+str(i);peer.register(c);(root/'workspace'/(c+'.txt')).write_text('OWNED_READ_CONTROL')
            fixture.plan(c,'reads'+str(i)+'__eval_probe',dict(token=c),'RECEIPT:'+c)
            if not gateway.request(c)['accepted'] or peer.receipts.get(c)!=1:raise RuntimeError('Native MCP read connection control failed')
        row.update(native_invoked=True,fixture_validated=True)
        calls=[];markers={}
        for i in range(4):
            item=token+'_READ_'+str(i);peer=peers[i%len(peers)];marker='READ_VALUE_'+str(i)+'_π_中文'
            peer.register(item);(root/'workspace'/(item+'.txt')).write_text(marker);markers[item]=marker
            calls.append(dict(tool='reads'+str(i%len(peers))+'__eval_probe',arguments=dict(token=item)))
        fixture.batch(token,calls,chain=mode=='chain');start=time.monotonic_ns();result=gateway.request(token)
        elapsed=(time.monotonic_ns()-start)/1e6;text=json.dumps(fixture.batch_returns.get(token,[]),ensure_ascii=False)
        check('all-four-owned-read-results-preserved',result['accepted'] and all(v in text for v in markers.values()))
        check('each-owned-read-dispatched-exactly-once',all(sum(p.receipts.get(k,0) for p in peers)==1 for k in markers))
        events=sorted([e for p in peers for e in p.events if e.get('token') in markers],key=lambda e:e['monotonic_ns'])
        starts={e['token']:e['monotonic_ns'] for e in events if e['kind']=='owned-read-start'}
        ends={e['token']:e['monotonic_ns'] for e in events if e['kind']=='owned-read-end'}
        if mode=='chain':check('dependency-results-arrive-before-next-dispatch',all(ends.get(calls[i]['arguments']['token'],10**30)<starts.get(calls[i+1]['arguments']['token'],0) for i in range(3)))
        overlap=sum(starts[a]<ends[b] and starts[b]<ends[a] for i,a in enumerate(markers) for b in list(markers)[i+1:] if a in starts and b in starts and a in ends and b in ends)
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,request=result,
            metadata=dict(mode=mode,read_count=4,owned_read_delay_ms=250,elapsed_ms=elapsed,overlapping_read_pairs=overlap,
                configured_mcp_servers=len(peers),connection_generations=[len(p.sessions) for p in peers],peak_calls_per_server=[p.peak_active for p in peers],
                scope='Same native task, four read-only MCP calls. S02 supplies each dependent call only after its preceding actual result. S03/S04 change only one versus two configured MCP peers; actual session generations are retained, not assumed. Parallel overlap is measured without assuming a mandatory parallelism guarantee.'),
            native_tool_results=fixture.batch_returns.get(token,[]),independent_read_events=events,provider_events=fixture.events,
            resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2500])
    finally:
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-3000:]
        for peer in peers:peer.close()
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
