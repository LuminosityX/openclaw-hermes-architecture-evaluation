"""Public trace lookup/export and objective record-level diagnosis.

The diagnosis function receives only native export bytes. External fixture truth
is supplied to the grader afterwards. Synthetic usage is a transport oracle,
never an actual provider price or model-quality measurement.
"""
import hashlib
import json
import shutil
import subprocess
import time

import mechanism_cases as mechanism
import pilot
import service_path_cases as service

SCENARIOS={f'OBS-07-S{i:02}':name for i,name in enumerate([
    'lookup','json-export','exact-error','task-usage','scoped-access','observer-overhead'],1)}


class UsageFixture(service.InstrumentedFixture):
    def __init__(self):
        self.reported_usage=[]
        super().__init__()

    def handler(self):
        base=super().handler(); owner=self
        class Handler(base):
            def do_POST(self):
                original=self.wfile
                class Stream:
                    def write(self,data):
                        if data==b'data: [DONE]\n\n':
                            usage=dict(prompt_tokens=41,completion_tokens=7,total_tokens=48)
                            owner.reported_usage.append(usage)
                            original.write(('data: '+json.dumps(dict(id='fixture-usage',object='chat.completion.chunk',
                                created=1760000000,model='fixture-model',choices=[],usage=usage))+'\n\n').encode())
                        return original.write(data)
                    def __getattr__(self,key):return getattr(original,key)
                self.wfile=Stream()
                try:return super().do_POST()
                finally:self.wfile=original

            def send(self,data,status=200):
                if isinstance(data,dict) and 'choices' in data and 'usage' in data:
                    data=dict(data,usage=dict(prompt_tokens=41,completion_tokens=7,total_tokens=48))
                    owner.reported_usage.append(data['usage'])
                return super().send(data,status)
        return Handler


def public_probe(root,session,role=None,methods=('chat.history',)):
    spec=root/'trace-wire-spec.json'
    operations=[]
    for method in methods:
        params=dict(sessionKey=session,limit=100,maxBytes=262144,toolResultMaxChars=32000) if method=='chat.history' else dict(key=session,range='all')
        operations.append(dict(method=method,params=params))
    pilot.save(spec,dict(shared_token=pilot.TOKEN,operations=operations,role=role))
    execution=subprocess.run([pilot.NODE,'/driver/trace_access_probe.mjs',str(spec)],capture_output=True,text=True,timeout=80)
    if not execution.stdout.strip():raise RuntimeError('Native trace wire probe emitted no result: '+execution.stderr[-1000:])
    result=json.loads(execution.stdout)
    if execution.returncode or result.get('harness_error') or not result.get('native_invoked'):
        raise RuntimeError('Native trace wire probe invalid: '+json.dumps(result)[:2000])
    return result


def record_diagnosis(native_export):
    """No scenario ID, action, fixture events or independent ledger is accepted."""
    data=json.loads(native_export)
    text=json.dumps(data,ensure_ascii=False)
    return dict(tool_failure='EVAL_COMPOSITION_TOOL_FAILURE' in text,
        exact_error='EVAL_COMPOSITION_TOOL_FAILURE' if 'EVAL_COMPOSITION_TOOL_FAILURE' in text else None,
        tool_identity_visible='eval_probe' in text,
        cause_boundary='tool-reported-failure' if 'EVAL_COMPOSITION_TOOL_FAILURE' in text else 'unknown',
        limitation='Rule-based record reconstruction; not a human usability study. Does not infer an external effect or root cause from absent logs.')


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario]; fixture=UsageFixture(); gateway=None
    token='PILOT_TRACE_'+scenario.replace('-','_')+'_U'+str(unit)
    report=dict(scenario_id=scenario,unit=unit,fixture_validated=False,native_invoked=False)
    assertions=[]
    def check(name,condition,evidence=('public-native-export','independent-fixture-ledger')):
        assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=list(evidence)))
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:service.configure(p))
        gateway.ready()
        control=token+'_CONTROL'; fixture.register(control)
        positive=gateway.request(control)
        if not positive['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Native positive receipt control failed')
        report.update(native_invoked=True,fixture_validated=True)
        session='agent:main:pilot:'+token.lower()
        fixture.register(token,action='throw' if mode=='exact-error' else 'effect')
        usage_start=len(fixture.reported_usage); began=time.monotonic_ns()
        task=gateway.request(token)
        task_usage=fixture.reported_usage[usage_start:]
        native=public_probe(root,session,methods=('chat.history','sessions.usage') if mode=='task-usage' else ('chat.history',))
        encoded=json.dumps(native,ensure_ascii=False,separators=(',',':')).encode()
        history=native['responses'][0]['result']
        check('public-history-method-returns-machine-readable-payload',history.get('ok') is True and isinstance(history.get('payload'),dict))
        text=json.dumps(history.get('payload',{}),ensure_ascii=False)
        check('task-identity-visible-in-history',token in text)
        metadata=dict(access='Public Gateway RPC, documented chat.history and sessions.usage',private_imports=0,core_edits=0,
            required_privilege='operator.admin owner for full trace; scoped roles are explicitly exercised in S05',
            export_bytes=len(encoded),export_sha256=hashlib.sha256(encoded).hexdigest(),
            lookup_wall_ms=(time.monotonic_ns()-began)/1e6)
        if mode=='json-export':
            exported=json.dumps(history.get('payload',{}),ensure_ascii=False,sort_keys=True).encode()
            check('json-export-roundtrip-is-lossless',json.loads(exported)==history.get('payload'))
            metadata['export_roundtrip_sha256']=hashlib.sha256(exported).hexdigest()
            metadata['roundtrip_scope']='Public native JSON export re-parsed by an independent consumer; no session-import claim.'
        elif mode=='exact-error':
            before=time.monotonic_ns(); diagnosis=record_diagnosis(encoded)
            metadata.update(diagnosis=diagnosis,diagnosis_ms=(time.monotonic_ns()-before)/1e6)
            check('exact-tool-arguments-visible',token in text and 'throw' in text and 'eval_probe' in text)
            check('exact-native-tool-error-diagnosable',diagnosis['tool_failure'] and diagnosis['tool_identity_visible'])
            check('independent-truth-agrees-with-failed-operation',not task['accepted'] and fixture.receipts.get(token,0)==0)
        elif mode=='task-usage':
            usage=native['responses'][1]['result']; usage_text=json.dumps(usage.get('payload',{}))
            expected=dict(input=sum(u['prompt_tokens'] for u in task_usage),output=sum(u['completion_tokens'] for u in task_usage))
            numbers=[]
            def visit(value,path=''):
                if isinstance(value,dict):
                    for key,child in value.items():
                        if isinstance(child,(int,float)):numbers.append(dict(path=path+'.'+key,value=child))
                        else:visit(child,path+'.'+key)
                elif isinstance(value,list):
                    for i,child in enumerate(value):visit(child,path+'['+str(i)+']')
            visit(usage.get('payload',{}))
            metadata.update(expected_fixture_usage=expected,native_usage_numbers=numbers,
                usage_scope='Nonzero synthetic usage tests task attribution and arithmetic only. No actual model cost is inferred.')
            check('native-usage-query-succeeds',usage.get('ok') is True)
            check('usage-linked-to-requested-session',session in usage_text)
            check('input-token-total-matches-independent-provider-reports',expected['input']>0 and any(n['value']==expected['input'] and any(k in n['path'].lower() for k in ['input','prompt']) for n in numbers))
            check('output-token-total-matches-independent-provider-reports',expected['output']>0 and any(n['value']==expected['output'] and any(k in n['path'].lower() for k in ['output','completion']) for n in numbers))
        elif mode=='scoped-access':
            reader=public_probe(root,session,role='read'); unscoped=public_probe(root,session,role='none')
            read_result=reader['responses'][0]['result']; denied=unscoped['responses'][0]['result']
            check('read-role-has-positive-trace-access',read_result.get('ok') is True)
            check('zero-scope-role-cannot-read-private-task-trace',denied.get('ok') is False and denied.get('error',{}).get('code')=='FORBIDDEN')
            metadata.update(reader=reader,unscoped=unscoped)
        elif mode=='observer-overhead':
            observed=[]
            for enabled in [False,True]:
                item=token+('_DEBUG' if enabled else '_SILENT');fixture.register(item)
                gateway.stop(); config=json.loads((root/'config.json').read_text());config['logging']['level']='debug' if enabled else 'silent';pilot.save(root/'config.json',config)
                gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready()
                before=service.owned_inventory(root,gateway.process.pid); result=gateway.request(item)
                observed.append(dict(observer_enabled=enabled,request={k:v for k,v in result.items() if k!='response_excerpt'},
                    disk_before=before,disk_after=service.owned_inventory(root,gateway.process.pid),resources=gateway.sampler.summary()))
                check('task-correct-with-observer-'+str(enabled),result['accepted'] and fixture.receipts.get(item)==1)
            metadata['matched_arms']=observed
            metadata['observer_scope']='Native debug file logging versus silent file logging. The external 200 ms resource sampler is identical in both arms. One pair per independent unit, not a statistically established overhead estimate.'
        else:check('documented-lookup-shows-independent-receipt','RECEIPT:'+token in text)
        report.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            native_export=native,metadata=metadata,independent_events=fixture.events,
            independent_receipts=fixture.receipts,resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:report.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2500])
    finally:
        if gateway:gateway.stop()
        fixture.close();shutil.rmtree(root,ignore_errors=True)
        report['owned_state_retained']=root.exists()
    return report
