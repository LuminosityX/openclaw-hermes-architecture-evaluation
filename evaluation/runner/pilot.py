"""Actual OpenClaw Gateway pilots in an externally bounded, ephemeral namespace."""

import argparse
import concurrent.futures
from collections import deque
import errno
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time

BASE = Path('/scratch')
NODE = '/toolchain/node'
CLI = '/runtime/node_modules/openclaw/openclaw.mjs'
TOKEN = 'synthetic-isolated-pilot-token'


def target_tool(token):
    if '_DENIED_' in token:
        return 'denied_probe'
    if '_SANDBOX_' in token:
        return 'exec'
    return 'probe__eval_probe' if '_MCP' in token else 'eval_probe'


def target_arguments(token,action):
    if '_SANDBOX_' not in token:
        return dict(token=token,action=action)
    import shlex
    code="import pathlib,os,json; p=pathlib.Path('scope-canary.txt'); print('SCOPE:'+json.dumps({'cwd':os.getcwd(),'had_canary':p.exists()})); "
    if '_WRITE_' in token:
        code+="p.write_text('SYNTHETIC_SCOPE_CANARY'); "
    code+="print('RECEIPT:'+"+repr(token)+")"
    return dict(command='python3 -c '+shlex.quote(code),yieldMs=10000)


def catalog_id(results,name):
    def visit(value,depth=0):
        if depth>12:
            return None
        if isinstance(value,dict):
            if value.get('name')==name and isinstance(value.get('id'),str):
                return value['id']
            for child in value.values():
                found=visit(child,depth+1)
                if found:
                    return found
        elif isinstance(value,list):
            for child in value:
                found=visit(child,depth+1)
                if found:
                    return found
        elif isinstance(value,str):
            try:
                parsed=json.loads(value)
            except ValueError:
                # Native MCP catalog output may wrap its JSON in an external-
                # content warning. Only extract catalog data, never instructions.
                decoder=json.JSONDecoder()
                for index,match in enumerate(re.finditer(r'[\[{]',value[:50000])):
                    if index>=64:
                        break
                    try:
                        parsed,_=decoder.raw_decode(value[match.start():])
                    except ValueError:
                        continue
                    if isinstance(parsed,(dict,list)):
                        found=visit(parsed,depth+1)
                        if found:
                            return found
                return None
            if isinstance(parsed,(dict,list)):
                return visit(parsed,depth+1)
        return None
    return visit(results)


def planned_tool_call(names,token,action,results,strategy='conservative'):
    """Use advertised direct tools or the pinned release's public catalog protocol."""
    name=target_tool(token)
    arguments=target_arguments(token,action)
    if '_DENIED_' in token and not results:
        dispatch=next((n for n in ['tool_call','dispatch_action'] if n in names),None)
        return (dispatch,dict(id=name,args=arguments)) if dispatch else (name,arguments)
    if name in names and not results:
        return name,arguments
    dispatch=next((n for n in ['tool_call','dispatch_action'] if n in names),None)
    if dispatch and 'tool_search' in names and 'tool_describe' in names:
        if strategy=='known':
            return (dispatch,dict(id=name,args=arguments)) if not results else None
        if not results:
            return 'tool_search',dict(query=name,limit=3)
        identifier=catalog_id(results,name)
        if not identifier:
            return None
        if len(results)==1:
            return 'tool_describe',dict(id=identifier)
        if len(results)==2:
            return dispatch,dict(id=identifier,args=arguments)
    return None


def save(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def storage_guard_check():
    directory=BASE/'storage-limit-probe'
    directory.mkdir()
    written=0
    exhausted=False
    try:
        chunk=b'\0'*(1024**2)
        try:
            for index in range(17):
                with (directory/str(index)).open('wb',buffering=0) as output:
                    for _ in range(8):
                        written+=output.write(chunk)
        except OSError as error:
            if error.errno!=errno.ENOSPC:
                raise
            exhausted=True
        usage=shutil.disk_usage(BASE)
        if not exhausted:
            raise RuntimeError('Storage guard did not enforce the requested bounded tmpfs')
        return dict(kernel_enospc_observed=True,tmpfs_total_bytes=usage.total,
                    bytes_written_before_rejection=written,probe_files_retained=False,
                    purpose='One-time kernel capacity check before product startup; not product disk usage.')
    finally:
        shutil.rmtree(directory)


class Fixture:
    def __init__(self):
        self.events = []
        self.lock = threading.Lock()
        self.fault_started = threading.Event()
        self.strategy='conservative'
        self.effect_delay_ms=150
        self.denied_attempted=set()
        self.provider_attempts={}
        self.server = ThreadingHTTPServer(('127.0.0.1',18080), self.handler())
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever,daemon=True).start()

    def event(self, kind, **values):
        with self.lock:
            record = dict(kind=kind, monotonic_ns=time.monotonic_ns(), **values)
            self.events.append(record)
            if kind=='provider-request':
                print('[pilot] provider '+values['token']+' tool_results='+str(values['tool_results']),file=sys.stderr,flush=True)
            return record

    def handler(self):
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):
                pass

            def send(self, data, status=200):
                encoded=json.dumps(data).encode()
                self.send_response(status)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_GET(self):
                self.send({'object':'list','data':[{'id':'fixture-model','object':'model'}]})

            def do_POST(self):
                raw=self.rfile.read(int(self.headers.get('Content-Length',0)))
                body=json.loads(raw)
                if self.path == '/effect':
                    metadata={key:body[key] for key in ['pid','uid','is_main_thread','thread_id','canary_readable'] if key in body}
                    owner.event('effect-start',token=body['token'],**metadata)
                    time.sleep(owner.effect_delay_ms/1000)
                    receipt='RECEIPT:'+body['token']
                    owner.event('effect-commit',token=body['token'],receipt=receipt)
                    return self.send(dict(receipt=receipt))
                if self.path == '/fault':
                    owner.event('fault-start',**body)
                    owner.fault_started.set()
                    return self.send({'ack':True})
                if not self.path.endswith('/chat/completions'):
                    return self.send({'error':'unrecognized local fixture path'},404)
                messages=body.get('messages',[])
                task_users=[i for i,m in enumerate(messages) if m.get('role')=='user' and re.search(r'PILOT_[A-Z0-9_]+',str(m.get('content','')))]
                last=max(task_users) if task_users else max((i for i,m in enumerate(messages) if m.get('role')=='user'),default=0)
                text=str(messages[last].get('content',''))
                match=re.search(r'PILOT_[A-Z0-9_]+',text)
                token=match.group() if match else 'PILOT_AUXILIARY'
                results=[m for m in messages[last+1:] if m.get('role')=='tool']
                schemas=body.get('tools',[])
                names=[t.get('function',{}).get('name','') for t in schemas]
                action=next((value for marker,value in [('_BLOCK_','block'),('_CRASH_','crash'),('_THROW_','throw'),('_CANARY_','canary'),('_PROFILE_','profile')] if marker in token),'effect')
                owner.event('provider-request',token=token,tool_results=len(results),tool_names=names,
                            payload_bytes=len(raw),tool_schema_bytes=len(json.dumps(schemas,ensure_ascii=False,separators=(',',':')).encode()),
                            message_bytes=len(json.dumps(messages,ensure_ascii=False,separators=(',',':')).encode()))
                calls=[]
                with owner.lock:
                    already_denied=token in owner.denied_attempted
                    if '_DENIED_' in token:
                        owner.denied_attempted.add(token)
                    owner.provider_attempts[token]=owner.provider_attempts.get(token,0)+1
                    attempts=owner.provider_attempts[token]
                if '_PLAIN_' in token:
                    content='ACCEPTED:'+token
                elif '_DENIED_' in token and already_denied:
                    content='CONTROLLED_DENIAL_FINISHED:'+token
                elif attempts>8:
                    owner.event('fixture-turn-limit',token=token)
                    content='FIXTURE_TURN_LIMIT:'+token
                else:
                    result_text=json.dumps(results,ensure_ascii=False)
                    if results:
                        owner.event('tool-result',token=token,receipt_visible=('RECEIPT:'+token in result_text),
                                    error_visible=bool(re.search(r'error|failed|not found|unavailable',result_text,re.I)),
                                    excerpt=result_text[:1500])
                    if 'RECEIPT:'+token in result_text:
                        content='ACCEPTED:'+token
                    else:
                        planned=planned_tool_call(names,token,action,results,owner.strategy)
                        if planned:
                            name,arguments=planned
                            calls=[dict(id='call_'+str(len(results))+'_'+token,type='function',function=dict(name=name,arguments=json.dumps(arguments)))]
                            content=None
                        else:
                            content=('TOOL_ERROR:' if results else 'MISSING_TOOL:')+','.join(names)
                message=dict(role='assistant',content=content)
                if calls:
                    message['tool_calls']=calls
                reason='tool_calls' if calls else 'stop'
                if not body.get('stream'):
                    return self.send(dict(id='fixture-'+token,object='chat.completion',created=int(time.time()),model='fixture-model',
                        choices=[dict(index=0,message=message,finish_reason=reason)],usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0)))
                self.send_response(200)
                self.send_header('Content-Type','text/event-stream')
                self.end_headers()
                delta=dict(role='assistant')
                if calls:
                    delta['tool_calls']=[dict(index=i,**c) for i,c in enumerate(calls)]
                else:
                    delta['content']=content
                try:
                    for d,finish in [(delta,None),({},reason)]:
                        chunk=dict(id='fixture-'+token,object='chat.completion.chunk',created=int(time.time()),model='fixture-model',choices=[dict(index=0,delta=d,finish_reason=finish)])
                        self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
                    self.wfile.write(b'data: [DONE]\n\n')
                    self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):
                    pass
        return Handler

    def close(self):
        self.server.shutdown()
        self.server.server_close()


PLUGIN = r'''
import fs from 'node:fs';
import inspector from 'node:inspector';
import {isMainThread,threadId} from 'node:worker_threads';
export default {
 id:'pilot-probe',name:'Pilot probe',
 register(api){
  api.registerTool({name:'eval_probe',label:'Pilot probe',description:'Execute a deterministic local pilot receipt operation',
   parameters:{type:'object',properties:{token:{type:'string'},action:{type:'string'}},required:['token']},
   async execute(id,args){
    if(args.action==='profile'&&!inspector.url())inspector.open(9229,'127.0.0.1',false);
    if(args.action==='canary')await fetch('http://127.0.0.1:18080/fault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:args.token,action:'canary',pid:process.pid,uid:process.getuid?.(),is_main_thread:isMainThread,thread_id:threadId})});
    if(args.action==='block'||args.action==='crash'||args.action==='throw'){
     await fetch('http://127.0.0.1:18080/fault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:args.token,action:args.action,pid:process.pid})});
     if(args.action==='crash')process.exit(42);
     if(args.action==='throw')throw new Error('SOURCE_FOLLOWUP_THROW');
     const until=Date.now()+600;while(Date.now()<until){}
    }
    const canary=args.action==='canary'?fs.readFileSync('/scratch/source-owned-canary','utf8')==='SYNTHETIC_SOURCE_CANARY':undefined;
    const response=await fetch('http://127.0.0.1:18080/effect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:args.token,pid:process.pid,uid:process.getuid?.(),is_main_thread:isMainThread,thread_id:threadId,canary_readable:canary})});
    const receipt=await response.json();
    return {content:[{type:'text',text:JSON.stringify(receipt)}]};
   }});
   api.registerTool({name:'denied_probe',description:'Synthetic forbidden-operation positive oracle',parameters:{type:'object',properties:{token:{type:'string'}},required:['token']},async execute(id,args){const r=await fetch('http://127.0.0.1:18080/effect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:args.token})});return {content:[{type:'text',text:JSON.stringify(await r.json())}]};}});
   // SOURCE_EXTRA_TOOLS
 }
};
'''


def configuration(root, concurrency=4, sandbox_scope=None, route='plugin', ssh_backend=False,tool_search=None,catalog_size=1):
    (root/'state').mkdir(parents=True)
    (root/'workspace').mkdir()
    config=dict(gateway=dict(mode='local',bind='loopback',port=18789,
                    auth=dict(mode='token',token=TOKEN),controlUi=dict(enabled=False),
                    http=dict(endpoints=dict(chatCompletions=dict(enabled=True)))),
        models=dict(providers=dict(fixture=dict(baseUrl='http://127.0.0.1:18080/v1',apiKey='synthetic-fixture',api='openai-completions',
            models=[dict(id='fixture-model',name='Deterministic local fixture',reasoning=False,input=['text'],contextWindow=128000,maxTokens=1024)]))),
        agents=dict(defaults=dict(workspace=str(root/'workspace'),model=dict(primary='fixture/fixture-model',fallbacks=[]),
                     maxConcurrent=concurrency,skipBootstrap=True,thinkingDefault='off',sandbox=dict(mode='off'))),
        cron=dict(enabled=False),logging=dict(level='debug',consoleLevel='warn',file=str(root/'gateway-native.log')),
        plugins=dict(allow=['pilot-probe'],load=dict(paths=[str(root/'plugin')]),entries={'pilot-probe':dict(enabled=True)}),
        tools=dict(allow=['eval_probe']))
    if sandbox_scope:
        config['agents']['defaults']['sandbox']=dict(mode='all',scope=sandbox_scope)
        config['tools']=dict(allow=['exec'])
        config['plugins']=dict(enabled=False)
        if ssh_backend:
            config['agents']['defaults']['sandbox'].update(backend='ssh',workspaceAccess='rw',
                ssh=dict(target='root@127.0.0.1:2222',workspaceRoot=str(root/'remote'),
                         strictHostKeyChecking=True,updateHostKeys=False,
                         identityFile='/scratch/ssh/client',knownHostsFile='/scratch/ssh/known_hosts'))
    elif route == 'plugin':
        plugin=root/'plugin'
        plugin.mkdir()
        save(plugin/'package.json',dict(name='pilot-probe',version='1.0.0',type='module',openclaw=dict(extensions=['./index.js'])))
        padding=[f'padding_probe_{i}' for i in range(catalog_size-1)]
        save(plugin/'openclaw.plugin.json',dict(id='pilot-probe',name='Pilot probe',activation=dict(onStartup=True),
             contracts=dict(tools=['eval_probe','denied_probe',*padding]),configSchema=dict(type='object',properties={},additionalProperties=False)))
        extra='\n'.join('api.registerTool('+json.dumps(dict(name=name,label=name,description='Synthetic unrelated catalog entry. '*8,
                         parameters=dict(type='object',properties=dict(text=dict(type='string',description='Synthetic schema field. '*16)))))[:-1]+",async execute(){return {content:[{type:'text',text:'unused'}]};}});" for name in padding)
        (plugin/'index.js').write_text(PLUGIN.replace('// SOURCE_EXTRA_TOOLS',extra))
        config['tools']['allow']=['eval_probe',*padding]
    elif route == 'mcp':
        config['plugins']=dict(enabled=False)
        config['mcp']=dict(servers=dict(probe=dict(transport='stdio',command='/usr/bin/python3',args=['/driver/mcp_probe.py'],supportsParallelToolCalls=True,requestTimeoutMs=10000)))
        config['tools']=dict(allow=['probe__eval_probe'])
    if tool_search is not None:
        config['tools']['toolSearch']=tool_search
    save(root/'config.json',config)
    return config


class Gateway:
    def __init__(self,root,**options):
        self.root=root
        self.config=configuration(root,**options)
        print('[pilot] starting Gateway '+root.name,file=sys.stderr,flush=True)
        self.log_tail=deque(maxlen=100)
        env=dict(os.environ,OPENCLAW_STATE_DIR=str(root/'state'),OPENCLAW_CONFIG_PATH=str(root/'config.json'),
                 OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_DISABLE_BUNDLED_PLUGINS='1')
        self.process=subprocess.Popen([NODE,CLI,'gateway','run','--bind','loopback','--port','18789'],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=env,start_new_session=True)
        self.reader=threading.Thread(target=self.read_log,daemon=True)
        self.reader.start()
        self.started=time.monotonic()
        self.sampler=Sampler(self.process.pid)

    def read_log(self):
        for line in self.process.stdout:
            self.log_tail.append(line[:2000])

    def ready(self):
        until=time.monotonic()+50
        while time.monotonic()<until:
            if self.process.poll() is not None:
                raise RuntimeError('Gateway exited: '+''.join(self.log_tail)[-5000:])
            connection=http.client.HTTPConnection('127.0.0.1',18789,timeout=.5)
            try:
                connection.request('GET','/readyz')
                response=connection.getresponse()
                response.read()
                if response.status==200:
                    print('[pilot] ready Gateway '+self.root.name,file=sys.stderr,flush=True)
                    return
            except (OSError,http.client.HTTPException):
                pass
            finally:
                connection.close()
            time.sleep(.1)
        raise RuntimeError('Gateway readiness timeout: '+''.join(self.log_tail)[-3000:])

    def request(self,token,session_key=None):
        begin=time.monotonic_ns()
        connection=http.client.HTTPConnection('127.0.0.1',18789,timeout=35)
        try:
            connection.request('POST','/v1/chat/completions',json.dumps(dict(model='openclaw',messages=[dict(role='user',content='Execute the requested deterministic operation for '+token)],user=token,stream=False)),
                               {'Content-Type':'application/json','Authorization':'Bearer '+TOKEN,'x-openclaw-session-key':'agent:main:pilot:'+(session_key or token).lower()})
            response=connection.getresponse()
            data=json.loads(response.read())
            content=''.join(str(c.get('message',{}).get('content','')) for c in data.get('choices',[]))
            return dict(token=token,status=response.status,accepted='ACCEPTED:'+token in content,
                        latency_ms=(time.monotonic_ns()-begin)/1e6,response_excerpt=json.dumps(data)[:1800])
        except (OSError,ValueError,http.client.HTTPException) as error:
            return dict(token=token,status=None,accepted=False,latency_ms=(time.monotonic_ns()-begin)/1e6,error=type(error).__name__)
        finally:
            connection.close()

    def stop(self):
        self.sampler.stop()
        if self.process.poll() is None:
            os.killpg(self.process.pid,signal.SIGTERM)
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid,signal.SIGKILL)
                self.process.wait()
        self.reader.join(timeout=1)


class Sampler:
    def __init__(self,pid):
        self.pid=pid
        self.done=threading.Event()
        self.samples=[]
        self.cpu={}
        self.thread=threading.Thread(target=self.sample,daemon=True)
        self.thread.start()

    def sample(self):
        ticks=os.sysconf('SC_CLK_TCK')
        while not self.done.is_set():
            processes={}
            for path in Path('/proc').glob('[0-9]*/stat'):
                try:
                    text=path.read_text()
                    fields=text[text.rfind(')')+2:].split()
                    processes[int(path.parent.name)]=(int(fields[1]),int(fields[11]),int(fields[12]),fields[19])
                except (OSError,ValueError,IndexError):
                    continue
            members={self.pid}
            while True:
                expanded=members|{pid for pid,values in processes.items() if values[0] in members}
                if expanded==members:
                    break
                members=expanded
            rss=pss=threads=fds=0
            for pid in members:
                try:
                    status=Path(f'/proc/{pid}/status').read_text()
                    match=re.search(r'VmRSS:\s+(\d+)',status)
                    rss+=int(match.group(1))*1024 if match else 0
                    match=re.search(r'Threads:\s+(\d+)',status)
                    threads+=int(match.group(1)) if match else 0
                    rollup=Path(f'/proc/{pid}/smaps_rollup').read_text()
                    match=re.search(r'\nPss:\s+(\d+)',rollup)
                    pss+=int(match.group(1))*1024 if match else 0
                    fds+=len(list(Path(f'/proc/{pid}/fd').iterdir()))
                    parent,user,system,start=processes[pid]
                    self.cpu[(pid,start)]=(user/ticks,system/ticks)
                except (OSError,ValueError,KeyError):
                    pass
            self.samples.append(dict(time_ns=time.monotonic_ns(),rss_bytes=rss,pss_bytes=pss,processes=len(members),threads=threads,open_fds=fds))
            if len(self.samples)>6000:
                self.samples=self.samples[::2]
            self.done.wait(.2)

    def stop(self):
        self.done.set()
        self.thread.join(timeout=1)

    def snapshot(self):
        values=dict(self.cpu)
        ticks=os.sysconf('SC_CLK_TCK')
        for key,prior in list(values.items()):
            pid,start=key
            try:
                text=Path(f'/proc/{pid}/stat').read_text()
                fields=text[text.rfind(')')+2:].split()
                if fields[19]==start:
                    values[key]=(max(prior[0],int(fields[11])/ticks),max(prior[1],int(fields[12])/ticks))
            except (OSError,IndexError,ValueError):
                pass
        return dict(user_seconds=sum(v[0] for v in values.values()),system_seconds=sum(v[1] for v in values.values()),
                    monotonic_ns=time.monotonic_ns(),known_processes=len(values))

    def summary(self):
        return dict(sample_interval_ms=200,sample_count=len(self.samples),
            product_process_tree_cpu_user_seconds=sum(v[0] for v in self.cpu.values()),
            product_process_tree_cpu_system_seconds=sum(v[1] for v in self.cpu.values()),
            peak_sampled_pss_bytes=max((s['pss_bytes'] for s in self.samples),default=None),
            peak_sampled_rss_sum_bytes=max((s['rss_bytes'] for s in self.samples),default=None),
            peak_sampled_processes=max((s['processes'] for s in self.samples),default=None),
            peak_sampled_threads=max((s['threads'] for s in self.samples),default=None),
            peak_sampled_open_fds=max((s['open_fds'] for s in self.samples),default=None),
            limitation='Sampled live Gateway descendants; short-lived processes or final CPU can be missed. RSS sum is not physical memory. Includes startup, warmup and collector perturbation.')


def native_evidence(root,tokens):
    found={token:dict(token_seen=False,receipt_seen=False,tables=[]) for token in tokens}
    inventories=[]
    for path in (root/'state').rglob('*.sqlite'):
        try:
            connection=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=.2)
            tables=[row[0] for row in connection.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
            inventories.append(dict(path=str(path.relative_to(root)),tables=tables))
            for table in tables:
                if not re.search('session|message|turn|tool|event',table,re.I):
                    continue
                escaped=table.replace('"','""')
                for row in connection.execute('select * from "'+escaped+'" limit 500'):
                    text=' '.join(v for v in row if isinstance(v,str))
                    for token in tokens:
                        if token in text:
                            found[token]['token_seen']=True
                            if table not in found[token]['tables']:
                                found[token]['tables'].append(table)
                        if 'RECEIPT:'+token in text:
                            found[token]['receipt_seen']=True
            connection.close()
        except sqlite3.Error as error:
            inventories.append(dict(path=str(path.relative_to(root)),error=type(error).__name__))
    log=root/'gateway-native.log'
    log_data=log.read_bytes() if log.exists() else b''
    for token in tokens:
        found[token]['native_log_token_seen']=token.encode() in log_data
    return dict(databases=inventories,tokens=found,native_log_bytes=len(log_data),native_log_sha256=hashlib.sha256(log_data).hexdigest(),
                limitation='Read-only native SQLite scan capped at 500 rows/table; text columns only. Coverage is a lower bound, not full trace certification.')


def allocation(root):
    paths=[p for p in root.rglob('*') if p.is_file()]
    return dict(apparent_bytes=sum(p.stat().st_size for p in paths),allocated_bytes=sum(p.stat().st_blocks*512 for p in paths),files=len(paths))


def peak_overlap(events):
    active=peak=0
    for event in events:
        active+=1 if event['kind']=='effect-start' else -1 if event['kind']=='effect-commit' else 0
        peak=max(peak,active)
    return peak


def queue_study(fixture,blocks):
    arms=[]
    for block in range(blocks):
        for cap in ([1,4] if block%2==0 else [4,1]):
            root=BASE/f'queue-{block}-{cap}'
            root.mkdir()
            gateway=Gateway(root,concurrency=cap)
            try:
                gateway.ready()
                warm=gateway.request(f'PILOT_WARM_{block}_{cap}')
                if not warm['accepted']:
                    raise RuntimeError('Queue positive control failed: '+json.dumps(warm))
                start_index=len(fixture.events)
                tokens=[f'PILOT_QUEUE_B{block}_C{cap}_T{i}' for i in range(8)]
                barrier=threading.Barrier(8)
                def request(token):
                    barrier.wait()
                    return gateway.request(token)
                begin=time.monotonic()
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                    results=list(pool.map(request,tokens))
                elapsed=time.monotonic()-begin
                events=fixture.events[start_index:]
                counts={t:sum(e['kind']=='effect-commit' and e.get('token')==t for e in events) for t in tokens}
                effective=json.loads((root/'config.json').read_text())['agents']['defaults']['maxConcurrent']
                arms.append(dict(block=block,max_concurrent=cap,effective_max_concurrent=effective,
                    attempts=8,accepted=sum(r['accepted'] for r in results),requests=results,
                    batch_seconds=elapsed,correct_goodput_per_s=sum(r['accepted'] for r in results)/elapsed,
                    effect_counts=counts,duplicate_effects=sum(max(0,c-1) for c in counts.values()),
                    peak_actual_effect_overlap=peak_overlap(events),events=events,
                    native_evidence=native_evidence(root,tokens),resources=gateway.sampler.summary(),state=allocation(root),
                    native_effective_config=effective_config(root),
                    valid=effective==cap and all(r['accepted'] for r in results) and all(c==1 for c in counts.values()) and peak_overlap(events)<=cap))
            finally:
                gateway.stop()
                shutil.rmtree(root)
    return dict(study='ARC-01',status='pilot-executed',independent_paired_blocks=blocks,arms=arms,
                valid=all(a['valid'] for a in arms),
                axes=dict(reliability='Receipt correctness observed; restart/durable-admission loss not tested.',
                    security='Not tested: no authority probes in this pilot.',performance='Batch goodput and end-to-end latency observed; queue wait and first output not separately attributed.',
                    resources_cost='Sampled product process tree and owned state; no paid tokens or price estimate.',
                    extensibility='Not applicable: same plugin contract in both arms.',observability='Native text receipt/token persistence compared with independent effect ledger; not full trace coverage.'),
                limitations=['Exploratory fixed 150 ms effect fixture and eight independent sessions; no production task capability conclusion.',
                    'Alternating arm order with fresh Gateway state; two blocks are not sufficient for a general statistical effect claim.'])


def effective_config(root):
    config=json.loads((root/'config.json').read_text())
    return dict(max_concurrent=config['agents']['defaults']['maxConcurrent'],
                sandbox=config['agents']['defaults']['sandbox'],tool_policy=config.get('tools'),
                config_sha256=hashlib.sha256((root/'config.json').read_bytes()).hexdigest())


def sandbox_study(fixture,ssh_backend=False,blocks=1):
    if ssh_backend:
        return ssh_sandbox_study(fixture,blocks)
    rows=[]
    for scope in ['agent','session']:
        root=BASE/('sandbox-'+scope)
        root.mkdir()
        gateway=Gateway(root,sandbox_scope=scope)
        try:
            gateway.ready()
            start=len(fixture.events)
            response=gateway.request('PILOT_SANDBOX_'+scope.upper())
            events=fixture.events[start:]
            rows.append(dict(scope=scope,response=response,events=events,log_tail=list(gateway.log_tail)[-15:],
                             native_effective_config=effective_config(root),resources=gateway.sampler.summary(),state=allocation(root)))
        finally:
            gateway.stop()
            shutil.rmtree(root)
    return dict(study='ARC-03',status='backend-unavailable',backend_binaries=dict(docker=shutil.which('docker'),podman=shutil.which('podman')),
                native_probes=rows,scope_tradeoff_measured=False,
                limitation='No backend or image installed/downloaded. Native configuration was probed, but isolation/resource tradeoff cannot be evaluated without a supported backend.')


class OwnedSSH:
    def __init__(self):
        directory=BASE/'ssh'
        directory.mkdir(mode=0o700)
        (BASE/'run/sshd').mkdir(parents=True)
        for name in ['host','client']:
            subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(directory/name)],check=True)
        (directory/'authorized_keys').write_bytes((directory/'client.pub').read_bytes())
        (directory/'authorized_keys').chmod(0o600)
        public=(directory/'host.pub').read_text().split()
        (directory/'known_hosts').write_text('[127.0.0.1]:2222 '+' '.join(public[:2])+'\n')
        (directory/'config').write_text('\n'.join(['Port 2222','ListenAddress 127.0.0.1',
            'HostKey /scratch/ssh/host','PidFile /scratch/ssh/pid',
            'AuthorizedKeysFile /scratch/ssh/authorized_keys','StrictModes no','UsePAM no',
            'PasswordAuthentication no','PermitRootLogin prohibit-password','LogLevel ERROR'])+'\n')
        self.log=(directory/'server.log').open('w')
        self.process=subprocess.Popen(['/usr/sbin/sshd','-D','-e','-f',str(directory/'config')],stdout=self.log,stderr=self.log,start_new_session=True)
        self.sampler=Sampler(self.process.pid)
        until=time.monotonic()+3
        while time.monotonic()<until:
            import socket
            try:
                with socket.create_connection(('127.0.0.1',2222),timeout=.1):
                    break
            except OSError:
                time.sleep(.05)
        else:
            self.stop()
            raise RuntimeError('Owned SSH server failed readiness')

    def stop(self):
        self.sampler.stop()
        if self.process.poll() is None:
            os.killpg(self.process.pid,signal.SIGTERM)
            self.process.wait(timeout=3)
        self.log.close()


def ssh_sandbox_study(fixture,blocks):
    server=OwnedSSH()
    arms=[]
    try:
        for block in range(blocks):
            for scope in (['agent','session'] if block%2==0 else ['session','agent']):
                root=BASE/f'ssh-sandbox-{block}-{scope}'
                root.mkdir()
                gateway=Gateway(root,sandbox_scope=scope,ssh_backend=True)
                try:
                    gateway.ready()
                    start=len(fixture.events)
                    write=gateway.request(f'PILOT_SANDBOX_WRITE_B{block}_{scope.upper()}',session_key='sandbox-writer')
                    read=gateway.request(f'PILOT_SANDBOX_READ_B{block}_{scope.upper()}',session_key='sandbox-reader')
                    revisit=gateway.request(f'PILOT_SANDBOX_REVISIT_B{block}_{scope.upper()}',session_key='sandbox-writer')
                    events=fixture.events[start:]
                    results=[e for e in events if e['kind']=='tool-result' and e['receipt_visible']]
                    decoded=[]
                    for event in results:
                        text=event['excerpt'].replace('\\"','"').replace('\\n','\n')
                        match=re.search(r'SCOPE:(\{[^\n}]+\})',text)
                        decoded.append(dict(token=event['token'],scope=json.loads(match.group(1)) if match else None))
                    arms.append(dict(block=block,scope=scope,write=write,read_other_session=read,revisit_writer=revisit,
                                     native_results=decoded,events=events,resources=gateway.sampler.summary(),state=allocation(root),
                                     remote_canary_paths=[str(p.relative_to(root)) for p in (root/'remote').rglob('scope-canary.txt')],
                                     native_effective_config=effective_config(root),log_tail=list(gateway.log_tail)[-12:],
                                     valid=write['accepted'] and read['accepted'] and revisit['accepted'] and len(decoded)==3 and all(d['scope'] is not None for d in decoded)))
                finally:
                    gateway.stop()
                    shutil.rmtree(root)
    finally:
        server.stop()
    return dict(study='ARC-03',status='pilot-executed',backend='ssh',independent_paired_blocks=blocks,arms=arms,
                valid=all(a['valid'] for a in arms),owned_ssh_resources=server.sampler.summary(),
                limitations=['Owned loopback OpenSSH target in the same bounded namespace; this measures native remote workspace ownership/reuse, not Docker or cross-host performance.',
                    'Same SSH OS identity can address sibling paths explicitly; different workspace roots are not hostile-tenant OS isolation.',
                    'Sandbox-enabled shell accesses only synthetic data; no privacy or malicious-code isolation certification.'])


def plugin_study(fixture,blocks):
    arms=[]
    for block in range(blocks):
        for route in (['plugin','mcp'] if block%2==0 else ['mcp','plugin']):
            root=BASE/f'plugin-{block}-{route}'
            root.mkdir()
            gateway=Gateway(root,route=route)
            try:
                gateway.ready()
                warm=gateway.request(f'PILOT_ROUTE_B{block}_{route.upper()}')
                if not warm['accepted']:
                    raise RuntimeError('Route positive control failed: '+json.dumps(warm)+' '+''.join(gateway.log_tail)[-1800:])
                baseline_neighbor=gateway.request(f'PILOT_PLAIN_BASE_B{block}_{route.upper()}')
                start=len(fixture.events)
                fixture.fault_started.clear()
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    blocked=pool.submit(gateway.request,f'PILOT_BLOCK_B{block}_{route.upper()}')
                    injected=fixture.fault_started.wait(15)
                    neighbor=gateway.request(f'PILOT_PLAIN_BLOCK_B{block}_{route.upper()}') if injected else None
                    blocked_result=blocked.result()
                block_events=fixture.events[start:]
                fixture.fault_started.clear()
                crash_start=len(fixture.events)
                crash=gateway.request(f'PILOT_CRASH_B{block}_{route.upper()}')
                fault_injected=fixture.fault_started.is_set()
                alive=gateway.process.poll() is None
                after=gateway.request(f'PILOT_PLAIN_AFTER_B{block}_{route.upper()}') if alive else None
                alive=gateway.process.poll() is None
                arms.append(dict(block=block,route=route,positive_control=warm,baseline_neighbor=baseline_neighbor,
                    block_injected=injected,blocked_request=blocked_result,neighbor_during_block=neighbor,block_events=block_events,
                    crash_injected=fault_injected,crash_request=crash,native_gateway_alive_after_fault=alive,
                    native_gateway_exit_code=gateway.process.poll(),neighbor_after_fault=after,
                    crash_events=fixture.events[crash_start:],
                    resources=gateway.sampler.summary(),state=allocation(root),native_effective_config=effective_config(root),
                    native_evidence=native_evidence(root,[warm['token'],blocked_result['token']]),
                    log_tail=list(gateway.log_tail)[-12:],valid=injected and fault_injected))
            finally:
                gateway.stop()
                shutil.rmtree(root)
    return dict(study='ARC-02',status='pilot-executed',independent_paired_blocks=blocks,arms=arms,
                valid=all(a['valid'] for a in arms),
                limitations=['Route comparison includes transport, protocol and interface differences; no pure causal isolation-cost conclusion.',
                    'Both routes execute trusted synthetic code; fault containment is not malicious-code or hostile-tenant isolation.',
                    'Controlled 600 ms CPU block and process exit42; no real-world failure probability or general latency quantile claim.'])


def smoke(fixture):
    root=BASE/'smoke'
    root.mkdir()
    gateway=Gateway(root)
    try:
        gateway.ready()
        plain=gateway.request('PILOT_PLAIN_CONTROL')
        effect=gateway.request('PILOT_EFFECT_CONTROL')
        return dict(study='smoke',plain=plain,effect=effect,events=fixture.events,
                    log_tail=list(gateway.log_tail)[-12:],state_bytes=sum(p.stat().st_size for p in root.rglob('*') if p.is_file()))
    finally:
        gateway.stop()
        shutil.rmtree(root)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--study',required=True)
    parser.add_argument('--blocks',type=int,default=2)
    parser.add_argument('--ssh-backend',action='store_true')
    args=parser.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
    for name in ['tmp','home','cache','run']:
        (BASE/name).mkdir()
    fixture=Fixture()
    report=dict(kind='exploratory-pilot',product='openclaw',paid_model_calls=0,calculated_cost_usd=None,
                studies=[],limitations=['Deterministic local provider; no task-reasoning or billing conclusion.'])
    try:
        report['storage_guard_check']=storage_guard_check()
        if args.study=='smoke':
            report['studies'].append(smoke(fixture))
        else:
            functions={'ARC-01':lambda:queue_study(fixture,args.blocks),
                       'ARC-03':lambda:sandbox_study(fixture,args.ssh_backend,args.blocks),
                       'ARC-02':lambda:plugin_study(fixture,args.blocks)}
            if args.study=='source-followup' or args.study.startswith('SRC-'):
                from source_followup import run
                run(sys.modules[__name__],fixture,args.blocks,args.study,report['studies'])
            else:
                selected=['ARC-01','ARC-03','ARC-02'] if args.study=='first-wave' else [args.study]
                for identifier in selected:
                    report['studies'].append(functions[identifier]())
    except Exception as error:
        report['harness_error']=str(error)
        report['fixture_failure_events']=fixture.events[-20:]
    finally:
        fixture.close()
        report['scratch_used_bytes']=shutil.disk_usage(BASE).used
        print(json.dumps(report,ensure_ascii=False))
    if 'harness_error' in report or any(s.get('valid') is False for s in report['studies']):
        raise SystemExit(1)


if __name__=='__main__':
    main()
