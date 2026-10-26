"""Probe the native budget surface before claiming a shared task-tree quota."""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import time
import uuid

from authorization_observation_cases import AuthorizationFixture
from effect_recovery_cases import wait_control
from mcp_http_fixture import McpHTTPFixture
import pilot
import privacy_cases
import service_path_cases as service

SCENARIOS={f'COST-05-S{i:02}':mode for i,mode in enumerate(['siblings','retry','tool-timeout','restart'],1)}


def contract_check():
    root=Path('/native-contracts');manifest=json.loads((root/'manifest.json').read_text())
    for entry in manifest['contracts']:
        raw=(root/Path(entry['path']).name).read_bytes()
        if len(raw)!=entry['bytes'] or hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise RuntimeError('Pinned budget support contract changed')
    docs=(root/'goal.md').read_text();code=(root/'goal-tools.ts').read_text()
    if 'session-goal guardrail, not a billing cap' not in docs or 'resolveGoalSessionScope' not in code or 'runSessionKey' not in code:
        raise RuntimeError('The versioned native budget contract does not establish the declared per-session scope')
    return manifest


def decoded_tool_records(messages):
    values=[]
    def visit(value,depth=0):
        if depth>8:return
        if isinstance(value,dict):
            values.append(value)
            for child in value.values():visit(child,depth+1)
        elif isinstance(value,list):
            for child in value:visit(child,depth+1)
        elif isinstance(value,str) and len(value)<=128*1024:
            try:parsed=json.loads(value)
            except ValueError:return
            if not isinstance(parsed,str):visit(parsed,depth+1)
    visit(messages);return values


def goal_from(messages):
    return next((node['goal'] for node in decoded_tool_records(messages) if isinstance(node.get('goal'),dict) and node['goal'].get('tokenBudget')==5000),None)


def missing_goal(messages):
    return any(node.get('status')=='missing' and node.get('goal') is None for node in decoded_tool_records(messages))


class BudgetFixture(AuthorizationFixture):
    def __init__(self):
        self.catalogues=[];self.batch_token=None;self.children=[];self.batch_ids=[];self.batch_emitted=False;self.retry_token=None;self.retry_injected=False
        self.focus_goal_token=None
        super().__init__()
    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def do_POST(self):
                if not self.path.endswith('/chat/completions'):return super().do_POST()
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4*1024**2:return self.send(dict(error='owned-budget-input-bound'),413)
                raw=self.rfile.read(size);body=json.loads(raw);tools=body.get('tools',[])
                owner.catalogues.append({t['function']['name']:t['function'].get('parameters') for t in tools if isinstance(t.get('function'),dict)})
                if owner.retry_token and owner.retry_token in raw.decode() and not owner.retry_injected:
                    owner.retry_injected=True;owner.event('actual-budget-probe-provider-503',token=owner.retry_token)
                    return self.send(dict(error=dict(message='Owned provider temporarily unavailable',type='server_error')),503)
                focus=owner.focus_goal_token
                focused=[i for i,message in enumerate(body.get('messages',[])) if message.get('role')=='user' and focus and focus in str(message.get('content',''))]
                if focus and focused:
                    identifier='owned_goal_read_'+hashlib.sha256(focus.encode()).hexdigest()[:20]
                    results=[m for m in body['messages'][focused[-1]+1:] if m.get('role')=='tool' and m.get('tool_call_id')==identifier]
                    names=[t.get('function',{}).get('name') for t in tools]
                    if results:
                        owner.tool_returns[focus]=results;message=dict(role='assistant',content='ACCEPTED:'+focus);finish='stop'
                    else:
                        tool='get_goal';arguments={}
                        if tool not in names and 'tool_call' in names:tool='tool_call';arguments=dict(id='get_goal',args={})
                        message=dict(role='assistant',content=None,tool_calls=[dict(id=identifier,type='function',function=dict(name=tool,arguments=json.dumps(arguments)))]);finish='tool_calls'
                    owner.event('actual-focused-native-goal-read',token=focus,tool_results=len(results))
                    common=dict(id='owned-native-goal-read',created=1760000000,model='fixture-model')
                    if not body.get('stream'):return self.send(dict(**common,object='chat.completion',choices=[dict(index=0,message=message,finish_reason=finish)],usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0)))
                    delta=dict(message)
                    if delta.get('tool_calls'):delta['tool_calls']=[dict(index=i,**v) for i,v in enumerate(delta['tool_calls'])]
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                    for value,reason in [(delta,None),({},finish)]:self.wfile.write(('data: '+json.dumps(dict(**common,object='chat.completion.chunk',choices=[dict(index=0,delta=value,finish_reason=reason)]))+'\n\n').encode())
                    self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush();return
                marked=[match.group() for message in body.get('messages',[]) if message.get('role')=='user' and (match:=re.search(r'PILOT_[A-Z0-9_]+',str(message.get('content',''))))]
                if owner.batch_token and marked and marked[-1]==owner.batch_token:
                    results=[m for m in body.get('messages',[]) if m.get('role')=='tool' and m.get('tool_call_id') in owner.batch_ids]
                    if results:owner.tool_returns[owner.batch_token]=results
                    calls=[]
                    if not owner.batch_emitted:
                        names=[t.get('function',{}).get('name') for t in tools]
                        for index,child in enumerate(owner.children):
                            tool='sessions_spawn';arguments=dict(task='Execute the deterministic operation for '+child,mode='run',cleanup='keep',label='owned-budget-scope-child')
                            if tool not in names and 'tool_call' in names:arguments=dict(id=tool,args=arguments);tool='tool_call'
                            calls.append(dict(id=owner.batch_ids[index],type='function',function=dict(name=tool,arguments=json.dumps(arguments))))
                        owner.batch_emitted=True;owner.event('actual-shared-parent-spawn-batch',token=owner.batch_token,child_count=len(calls))
                    message=dict(role='assistant',content=None,tool_calls=calls) if calls else dict(role='assistant',content='ACCEPTED:'+owner.batch_token)
                    finish='tool_calls' if calls else 'stop';common=dict(id='owned-budget-scope',created=1760000000,model='fixture-model')
                    if not body.get('stream'):return self.send(dict(**common,object='chat.completion',choices=[dict(index=0,message=message,finish_reason=finish)],usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0)))
                    delta=dict(message)
                    if calls:delta['tool_calls']=[dict(index=i,**call) for i,call in enumerate(calls)]
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                    for value,reason in [(delta,None),({},finish)]:self.wfile.write(('data: '+json.dumps(dict(**common,object='chat.completion.chunk',choices=[dict(index=0,delta=value,finish_reason=reason)]))+'\n\n').encode())
                    self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush();return
                original=self.rfile;self.rfile=io.BytesIO(raw)
                try:return super().do_POST()
                finally:self.rfile=original
        return Handler


class TimeoutPeer(McpHTTPFixture):
    def __init__(self):self.delayed=None;super().__init__()
    def response(self,body,session_id):
        token=body.get('params',{}).get('arguments',{}).get('token')
        if body.get('method')=='tools/call' and token==self.delayed:
            self.event('actual-owned-timeout-call-admitted',token=token);time.sleep(2)
        return super().response(body,session_id)


def configure(root,mode):
    config=service.configure(root);config['tools']['allow'].extend(['create_goal','get_goal','sessions_spawn'])
    config['tools']['subagents']=dict(tools=dict(allow=['get_goal','eval_probe']))
    config['agents']['defaults']['subagents']=dict(maxConcurrent=2,maxSpawnDepth=1)
    if mode=='tool-timeout':
        config['mcp']=dict(servers=dict(budgetpeer=dict(transport='streamable-http',url='http://127.0.0.1:18085/mcp',requestTimeoutMs=500,connectionTimeoutMs=5000)))
        config['tools']['allow'].append('budgetpeer__eval_probe')
    pilot.save(root/'config.json',config);return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];token='PILOT_BUDGET_SCOPE_'+scenario.replace('-','_')+'_U'+str(unit);session='agent:main:pilot:'+token.lower()
    fixture=BudgetFixture();peer=TimeoutPeer() if mode=='tool-timeout' else None;gateway=None;metadata={};requests=[]
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def read_goal(item):
        fixture.plan(item,'get_goal',{},'');fixture.focus_goal_token=item
        try:
            result=gateway.request(item,session_key=token.lower());requests.append(result);return goal_from(fixture.tool_returns.get(item,[]))
        finally:fixture.focus_goal_token=None
    try:
        contracts=contract_check();gateway=pilot.Gateway(root,configurer=lambda p:configure(p,mode));gateway.ready();wait_control(gateway,fixture,token+'_READY')
        initialized=token+'_SESSION';fixture.register(initialized)
        if not gateway.request(initialized,session_key=token.lower())['accepted']:raise RuntimeError('Native budget capability session initialization failed')
        created=token+'_CREATE';fixture.plan(created,'create_goal',dict(objective='Owned budget API scope probe',token_budget=5000),'')
        result=privacy_cases.request(gateway,created,session,'The user explicitly requests a new goal for this capability probe and an explicit token budget of 5000.');requests.append(result)
        goal=goal_from(fixture.tool_returns.get(created,[]))
        if not result['accepted'] or not goal or not goal.get('id'):raise RuntimeError('Actual supported per-session native goal-budget positive control failed')
        metadata['native_created_session_goal']=goal
        pause=privacy_cases.wire(root,[dict(method='sessions.goal.update',params=dict(sessionKey=session,goalId=goal['id'],operationId=str(uuid.uuid4()),issuedAtMs=int(time.time()*1000),action='pause',note='Operator pauses the capability probe goal; no autonomous work is requested'))])
        if not pause['responses'][0]['result'].get('ok'):raise RuntimeError('Native operator goal pause control failed')
        metadata['native_operator_pause']=pause
        parent=read_goal(token+'_PARENT_GOAL')
        if not parent or parent['id']!=goal['id'] or parent.get('status')!='paused':raise RuntimeError('Native paused goal and its budget could not be independently read')
        fixture.batch_token=token+'_SIBLINGS';fixture.children=[token+'_CHILD_1',token+'_CHILD_2'];fixture.batch_ids=['owned_budget_'+hashlib.sha256((token+str(i)).encode()).hexdigest()[:20] for i in range(2)]
        for child in fixture.children:fixture.child_tokens.add(child);fixture.plan(child,'get_goal',{},'')
        result=gateway.request(fixture.batch_token,session_key=token.lower());requests.append(result)
        deadline=time.monotonic()+25
        while time.monotonic()<deadline and not all(fixture.tool_returns.get(child) for child in fixture.children):time.sleep(.1)
        child_snapshots=[decoded_tool_records(fixture.tool_returns.get(child,[])) for child in fixture.children]
        metadata.update(actual_sibling_spawn_results=fixture.tool_returns.get(fixture.batch_token,[]),actual_sibling_goal_snapshots=child_snapshots)
        if not all(missing_goal(fixture.tool_returns.get(child,[])) for child in fixture.children):raise RuntimeError('Real sibling get_goal probes did not establish their independent session scope')
        if mode=='retry':
            item=token+'_RETRY';fixture.retry_token=item;fixture.register(item);result=gateway.request(item);requests.append(result)
            if not fixture.retry_injected or not result['accepted'] or fixture.receipts.get(item)!=1:raise RuntimeError('Actual native provider retry positive probe failed')
            metadata['actual_retry_completed']=True
        elif mode=='tool-timeout':
            control=token+'_MCP_CONTROL';peer.register(control);fixture.plan(control,'budgetpeer__eval_probe',dict(token=control),'RECEIPT:'+control)
            if not gateway.request(control)['accepted'] or peer.receipts.get(control)!=1:raise RuntimeError('Actual native timeout-tool transport positive control failed')
            item=token+'_TOOL_TIMEOUT';peer.register(item);peer.delayed=item;fixture.plan(item,'budgetpeer__eval_probe',dict(token=item),'');result=gateway.request(item);requests.append(result)
            returned=json.dumps(fixture.tool_returns.get(item,[]))
            if not any(e['kind']=='actual-owned-timeout-call-admitted' for e in peer.events) or not re.search(r'timed out|timeout',returned,re.I):raise RuntimeError('Actual native MCP time limit was not exercised')
            metadata['native_tool_timeout_result']=fixture.tool_returns.get(item,[])
        elif mode=='restart':
            old_pid=gateway.process.pid;gateway.stop();gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready();wait_control(gateway,fixture,token+'_RESTART_READY')
            restored=read_goal(token+'_RESTORED_GOAL')
            if gateway.process.pid==old_pid or not restored or restored['id']!=goal['id'] or restored['tokenBudget']!=5000:raise RuntimeError('Actual native per-session goal budget did not survive its restart control')
            metadata['native_restored_session_goal']=restored
        contract=next(c for c in contracts['contracts'] if c['path']=='src/agents/tools/goal-tools.ts')
        row.update(state='unsupported',native_invoked=True,fixture_validated=True,probe_attempted=True,native_capability_absent=True,
            exclusion_reason='capability-not-provided',native_contract=dict(target_commit=contracts['target_commit'],reference=contract['reference'],sha256=contract['sha256']),
            capability_evidence=['actual-native-parent-session-goal-and-budget','two-real-sibling-get-goal-results-with-independent-scope','pinned-create-goal-schema-and-resolveGoalSessionScope','pinned-goal-contract-distinguishes-session-guardrail-from-billing-cap'],
            metadata=metadata,native_tool_returns=fixture.tool_returns,native_model_goal_schemas=[{name:schema for name,schema in catalog.items() if name in {'create_goal','get_goal'}} for catalog in fixture.catalogues],
            resources=gateway.sampler.summary(),paid_model_calls=0,
            scope='Verified nonapplicability of the required builtin shared task-tree budget pool in the pinned native session-goal surface. Per-session token guardrails, separate child contexts, retry, tool timeouts and saved goal state were actually probed. These are capability checks, not claimed competing-pool overshoot measurements, a custom quota plugin, provider billing caps or accepted statistical performance samples.')
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2400],metadata=metadata)
    finally:
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-4000:]
        row.update(requests=requests,native_tool_returns=fixture.tool_returns,independent_events=fixture.events,independent_effects=fixture.receipts,independent_tool_events=peer.events if peer else [])
        if peer:peer.close()
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
