"""Agent-visible task tools. Expected answers stay on the hosted controller."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading

import pilot

PLUGIN=r'''
export default {id:'task-lab',name:'Versioned synthetic task toolkit',register(api){
 const invoke=async(endpoint,args)=>{
   const response=await fetch('http://127.0.0.1:18080/'+endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(args)});
   const data=await response.json();
   return {content:[{type:'text',text:JSON.stringify({http_status:response.status,...data})}],isError:response.status>=400};
 };
 api.registerTool({name:'task_files',description:'List/read task files, write the requested deliverable, or run supplied public tests. Paths are task-relative.',
  parameters:{type:'object',properties:{op:{type:'string',enum:['list','read','write','test']},path:{type:'string'},content:{type:'string'}},required:['op']},
  async execute(id,args){return invoke('task-files',args);}});
 api.registerTool({name:'task_service',description:'Synthetic order service: prepare(order_id, amount_cents), commit(order_id, idempotency_key), status(order_id). An acknowledgment may be lost after a commit; use status and stable idempotency keys.',
  parameters:{type:'object',properties:{action:{type:'string',enum:['prepare','commit','status']},order_id:{type:'string'},amount_cents:{type:'integer'},idempotency_key:{type:'string'}},required:['action','order_id']},
  async execute(id,args){return invoke('task-service',args);}});
}};
'''


def configure(root,task,thinking=False):
    config=pilot.configuration(root,tool_search=False)
    plugin=root/'task-plugin';plugin.mkdir()
    pilot.save(plugin/'package.json',dict(name='task-lab',version='1.0.0',type='module',openclaw=dict(extensions=['./index.js'])))
    pilot.save(plugin/'openclaw.plugin.json',dict(id='task-lab',name='Versioned synthetic task toolkit',activation=dict(onStartup=True),contracts=dict(tools=['task_files','task_service']),configSchema=dict(type='object',properties={},additionalProperties=False)))
    (plugin/'index.js').write_text(PLUGIN)
    provider=config['models']['providers'].pop('fixture')
    provider.update(baseUrl='http://127.0.0.1:18081/v1',apiKey='synthetic-relay-placeholder')
    provider['models'][0].update(id='deepseek-flash',name='User selected DeepSeek Flash',reasoning=thinking,contextWindow=1000000,maxTokens=16384)
    config['models'].update(mode='replace',providers={'deepseek':provider})
    config['agents']['defaults']['model']['primary']='deepseek/deepseek-flash'
    config['agents']['defaults']['thinkingDefault']='high' if thinking else 'off'
    config['plugins']=dict(allow=['task-lab','deepseek'],load=dict(paths=[str(plugin),'/runtime/node_modules/@openclaw/deepseek-provider']),entries={'task-lab':dict(enabled=True),'deepseek':dict(enabled=True)})
    config['tools']=dict(allow=['task_files','task_service'],toolSearch=False)
    for name,content in task['files'].items():
        if Path(name).name!=name: raise ValueError('Task files must have simple names')
        (root/'workspace'/name).write_text(content)
    pilot.save(root/'config.json',config)
    return config


class TaskFixture(pilot.Fixture):
    def __init__(self,root,task):
        self.task_root=Path(root)
        self.task=task
        self.task_events=[]
        self.task_lock=threading.Lock()
        self.receipts={}
        self.prepared=None
        self.ack_lost=False
        super().__init__()

    def record(self,kind,**values):
        event=self.event(kind,task_id=self.task['task_id'],**values)
        event=dict(event,sequence=len(self.task_events)+1)
        self.task_events.append(event)
        return event

    def files(self,args):
        op=args.get('op')
        names=set(self.task['files'])|{self.task['artifact']}
        if op=='list': return 200,dict(files=sorted(names))
        if op=='test':
            if 'public_tests.py' not in self.task['files']: return 400,dict(error='No supplied public executable tests; check the task contract')
            with tempfile.TemporaryFile() as output:
                process=subprocess.Popen(['/usr/bin/python3','-I','-c',"import runpy,sys;sys.path.insert(0,'.');runpy.run_path('public_tests.py',run_name='__main__')"],cwd=self.task_root/'workspace',
                    stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
                output.seek(0);raw=output.read(8192)
            self.record('public-test-run',returncode=process.returncode)
            return 200,dict(returncode=process.returncode,output=raw.decode(errors='replace'))
        name=args.get('path')
        if name not in names: return 403,dict(error='Only supplied task files and the named deliverable are accessible')
        path=self.task_root/'workspace'/name
        if path.is_symlink(): return 403,dict(error='Symlink task files are not part of the fixture contract')
        if op=='read':
            if not path.is_file(): return 404,dict(error='Task file does not exist')
            return 200,dict(path=name,content=path.read_text()[:128*1024])
        if op=='write':
            content=args.get('content')
            if name!=self.task['artifact'] or not isinstance(content,str) or len(content.encode())>128*1024:
                return 403,dict(error='Only the named deliverable can be written within its byte limit')
            path.write_text(content)
            self.record('artifact-write',path=name,bytes=len(content.encode()))
            return 200,dict(written=True,path=name)
        return 400,dict(error='Unknown task file operation')

    def service(self,args):
        if 'service_fixture' not in self.task: return 403,dict(error='This task has no order service')
        expected=self.task['service_fixture']
        if args.get('order_id')!=expected['order_id']: return 403,dict(error='Order is outside this task')
        action=args.get('action')
        if action=='prepare':
            if type(args.get('amount_cents')) is not int or args['amount_cents']!=expected['amount_cents']:
                return 400,dict(error='Order amount does not match the input')
            self.prepared=args['amount_cents']
            self.record('order-prepared',order_id=args['order_id'],amount_cents=self.prepared)
            return 200,dict(prepared=True,order_id=args['order_id'])
        if action=='status':
            self.record('status-read',order_id=args['order_id'])
            return 200,dict(receipts=list(self.receipts.values()))
        if action=='commit':
            key=args.get('idempotency_key')
            if self.prepared is None or not isinstance(key,str) or not 1<=len(key)<=128:
                return 400,dict(error='Prepare first and supply a stable idempotency key')
            if key not in self.receipts:
                receipt=dict(order_id=args['order_id'],amount_cents=self.prepared,receipt_id='receipt-'+str(len(self.receipts)+1))
                self.receipts[key]=receipt
                self.record('commit-effect',**receipt)
                if expected.get('lose_first_commit_ack') and not self.ack_lost:
                    self.ack_lost=True
                    self.record('commit-ack-lost',order_id=args['order_id'])
                    return 503,dict(error='Synthetic acknowledgment lost after server-side processing; inspect order status before another operation')
            return 200,self.receipts[key]
        return 400,dict(error='Unknown service action')

    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def do_POST(self):
                if self.path not in {'/task-files','/task-service'}: return super().do_POST()
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=256*1024: return self.send(dict(error='Task fixture request byte limit'),413)
                try:
                    args=json.loads(self.rfile.read(size))
                    with owner.task_lock:
                        owner.record('task-tool-call',operation=args.get('op') or args.get('action'),path=args.get('path'))
                        status,result=owner.files(args) if self.path=='/task-files' else owner.service(args)
                    return self.send(result,status)
                except (ValueError,TypeError,OSError): return self.send(dict(error='Invalid task fixture operation'),400)
        return Handler


def selfcheck(task):
    """Positive and denied controls in a separate scratch fixture, then delete it."""
    with tempfile.TemporaryDirectory(prefix='task-fixture-control-',dir='/scratch') as directory:
        root=Path(directory)
        (root/'workspace').mkdir()
        for name,content in task['files'].items(): (root/'workspace'/name).write_text(content)
        probe=object.__new__(TaskFixture)
        probe.task_root=root;probe.task=task;probe.task_events=[];probe.events=[]
        probe.lock=threading.Lock();probe.receipts={};probe.prepared=None;probe.ack_lost=False
        assert probe.files(dict(op='read',path=next(iter(task['files']))))[0]==200
        assert probe.files(dict(op='read',path='/etc/passwd'))[0]==403
        assert probe.files(dict(op='write',path=task['artifact'],content='synthetic-control'))[0]==200
        assert probe.files(dict(op='read',path=task['artifact']))[1]['content']=='synthetic-control'
        if 'service_fixture' in task:
            expected=task['service_fixture']
            assert probe.service(dict(action='prepare',order_id='outside-task',amount_cents=expected['amount_cents']))[0]==403
            assert probe.service(dict(action='prepare',order_id=expected['order_id'],amount_cents=expected['amount_cents']))[0]==200
            args=dict(action='commit',order_id=expected['order_id'],idempotency_key='control-stable-key')
            assert probe.service(args)[0]==503
            assert probe.service(args)[0]==200
            assert len([e for e in probe.task_events if e['kind']=='commit-effect'])==1
            assert probe.service(dict(action='status',order_id=expected['order_id']))[1]['receipts']
    return dict(valid=True,read_write_positive_control=True,outside_path_denied=True,
                service_lost_ack_and_idempotency_control='service_fixture' in task,control_state_retained=False)
