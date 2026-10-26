"""Swap a public context engine while checking native-owned transcript invariants."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from effect_recovery_cases import wait_control
from operation_fixture import OperationFixture
import pilot
import privacy_cases
import service_path_cases as service

ENGINE='eval-context-reference'
SCENARIOS={f'EXT-04-S{i:02}':mode for i,mode in enumerate(['normal','context-budget','restart','disabled'],1)}


class ContextFixture(OperationFixture):
    def __init__(self):self.context_events=[];super().__init__()
    def handler(self):
        base=super().handler();owner=self
        class Handler(base):
            def do_POST(self):
                if self.path!='/context-event':return super().do_POST()
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=32768:return self.send(dict(error='bounded-context-event'),413)
                data=json.loads(self.rfile.read(size))
                if data.get('engine_id')!=ENGINE:return self.send(dict(error='owned-reference-engine-only'),403)
                event=owner.event('reference-context-event',**{k:v for k,v in data.items() if k!='kind'},event_type=data.get('kind'))
                owner.context_events.append(event);return self.send(dict(observed=True))
        return Handler


def configure(root,enabled=True):
    config=service.configure(root);config['models']['providers']['fixture']['models'][0]['contextWindow']=20000
    config['agents']['defaults']['compaction']=dict(memoryFlush=dict(enabled=False))
    if enabled:
        plugin=root/'context-reference';plugin.mkdir()
        pilot.save(plugin/'package.json',dict(name=ENGINE,version='1.0.0',type='module',openclaw=dict(extensions=['./index.mjs'])))
        pilot.save(plugin/'openclaw.plugin.json',dict(id=ENGINE,kind='context-engine',activation=dict(onStartup=True),
            configSchema=dict(type='object',properties=dict(state_path=dict(type='string')),required=['state_path'],additionalProperties=False)))
        shutil.copyfile(Path(__file__).with_name('context_reference.mjs'),plugin/'index.mjs')
        config['plugins']['allow'].append(ENGINE);config['plugins']['load']['paths'].append(str(plugin))
        config['plugins']['entries'][ENGINE]=dict(enabled=True,config=dict(state_path=str(root/'workspace/.eval-reference-context.json')))
        config['plugins']['slots']=dict(contextEngine=ENGINE)
    pilot.save(root/'config.json',config);return config


def checkpoint(root):
    path=root/'workspace/.eval-reference-context.json'
    if not path.is_file():return dict(exists=False,keys=[])
    raw=path.read_bytes()
    if len(raw)>512*1024:raise RuntimeError('Owned reference checkpoint exceeds its declared bound')
    state=json.loads(raw)
    return dict(exists=True,keys=sorted(state['commits']),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
        sessions=sorted({r['session_key'] for r in state['commits'].values() if r.get('session_key')}))


def toggle(root,enabled):
    env=dict(os.environ,OPENCLAW_STATE_DIR=str(root/'state'),OPENCLAW_CONFIG_PATH=str(root/'config.json'),OPENCLAW_DISABLE_BUNDLED_PLUGINS='1')
    command=[pilot.NODE,pilot.CLI,'plugins','enable' if enabled else 'disable',ENGINE]
    if enabled:command.append('--accept-capabilities')
    result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=40)
    if result.returncode:raise RuntimeError('Native context component toggle failed: '+result.stderr[-1200:])
    return dict(returncode=result.returncode,stdout=result.stdout[-1500:],stderr=result.stderr[-1500:])


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];token='PILOT_CONTEXT_'+scenario.replace('-','_')+'_U'+str(unit)
    fixture=ContextFixture();gateway=None;assertions=[];metadata={};requests=[];exports=[]
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['actual-public-context-engine-callbacks','independent-owned-checkpoint-and-receipt-ledger','native-public-transcript-and-model-input']))
    def task(item):
        fixture.plan(item,'eval_probe',dict(token=item),'RECEIPT:'+item)
        result=gateway.request(item,session_key=token.lower());requests.append(result);return result
    try:
        arms=['legacy','reference'] if mode=='normal' else ['reference'];arm_results=[]
        for arm in arms:
            directory=root/arm;gateway=pilot.Gateway(directory,configurer=lambda p:configure(p,arm=='reference'));gateway.ready()
            control=token+'_'+arm.upper()+'_CONTROL';control_result=task(control)
            if not control_result['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Native context arm task positive control failed')
            if arm=='reference':
                if not any(e['event_type']=='assemble' for e in fixture.context_events):raise RuntimeError('Selected reference context engine did not actually assemble native context')
                before=checkpoint(directory)
                if not before['exists'] or not before['keys']:raise RuntimeError('Native accepted-turn contract did not invoke reference commit persistence')
            row.update(native_invoked=True,fixture_validated=True)
            if mode=='context-budget':
                for index in range(8):
                    item=token+'_PLAIN_'+str(index);fixture.register(item)
                    # Public varied text, not an oracle-specific summary or a hidden answer.
                    filler=' '.join(hashlib.sha256((str(index)+':'+str(i)).encode()).hexdigest()[:12] for i in range(1300))[:16384]
                    result=privacy_cases.request(gateway,item,'agent:main:pilot:'+token.lower(),private_prompt='Public context workload '+filler);requests.append(result)
                    if not result['accepted']:raise RuntimeError('Reference bounded-assembly primer failed before the registered context condition was established')
                conditions=[e for e in fixture.context_events if e['event_type']=='assemble' and e['input_estimated_tokens']>e['supplied_budget']]
                if not conditions:raise RuntimeError('Registered reference character-estimate context budget was never actually crossed')
                check('reference-assembly-reduces-whole-history-under-supplied-budget',all(e['output_estimated_tokens']<=e['supplied_budget'] and e['output_messages']<e['input_messages'] for e in conditions))
                metadata['budget_crossing_events']=conditions
            elif mode=='restart':
                old_pid=gateway.process.pid;old_keys=set(before['keys']);gateway.stop()
                gateway=pilot.Gateway(directory,configurer=service.reuse);gateway.ready();wait_control(gateway,fixture,token+'_RESTART_READY')
                reloaded=checkpoint(directory);metadata.update(pre_restart_checkpoint=before,post_restart_checkpoint=reloaded,native_gateway_pid_changed=old_pid!=gateway.process.pid)
                check('component-checkpoint-and-native-session-survive-restart',old_keys<=set(reloaded['keys']) and old_pid!=gateway.process.pid)
            elif mode=='disabled':
                gateway.stop();metadata['native_disable']=toggle(directory,False);store_before=checkpoint(directory);event_boundary=len(fixture.context_events)
                gateway=pilot.Gateway(directory,configurer=service.reuse);gateway.ready();wait_control(gateway,fixture,token+'_DISABLED_READY')
                item=token+'_DISABLED';disabled_result=task(item);store_after=checkpoint(directory)
                check('disabled-selected-component-falls-back-to-working-native-context',disabled_result['accepted'] and fixture.receipts.get(item)==1)
                check('disabled-component-neither-assembles-nor-writes-checkpoint',len(fixture.context_events)==event_boundary and store_before==store_after)
                gateway.stop();metadata['native_enable']=toggle(directory,True);gateway=pilot.Gateway(directory,configurer=service.reuse);gateway.ready();wait_control(gateway,fixture,token+'_REENABLED_READY')
                check('native-slot-preference-preserved',json.loads((directory/'config.json').read_text())['plugins']['slots']['contextEngine']==ENGINE)
            item=token+'_'+arm.upper()+'_FINAL';result=task(item)
            check(arm+'-task-has-one-independent-effect',result['accepted'] and fixture.receipts.get(item)==1)
            session='agent:main:pilot:'+token.lower();exported=privacy_cases.history(directory,session);exports.append(exported)
            text=json.dumps(exported)
            check(arm+'-core-transcript-retains-accepted-user-and-tool-records',control in text and 'RECEIPT:'+control in text and item in text)
            if arm=='reference':
                after=checkpoint(directory)
                check('reference-checkpoint-is-owned-and-accepted-turns-advance',after['exists'] and len(after['keys'])>len(before['keys']))
                if mode=='restart':check('actual-model-context-retains-pre-restart-native-history',control in json.dumps(fixture.native_inputs.get(item,[])))
                metadata['final_checkpoint']=after
            arm_results.append(dict(arm=arm,task=result,resources=gateway.sampler.summary(),config_sha256=hashlib.sha256((directory/'config.json').read_bytes()).hexdigest()))
            gateway.stop();gateway=None
        metadata.update(mode=mode,arms=arm_results,reference_source_sha256=hashlib.sha256(Path(__file__).with_name('context_reference.mjs').read_bytes()).hexdigest(),
            state_scope='Reference component writes only its owned 512 KiB serial single-Gateway JSON commit index. Core transcript IDs, admission, tool authorization and native databases are untouched.',
            context_budget_scope='Conservative UTF-8 JSON bytes/4 estimate against the actual host-supplied context budget; no actual tokenizer-limit, model-quality or summarization-quality claim.',
            compaction_scope='The reference bounds assembled whole user turns and returns no transcript rewrite or fabricated summary. Paid native compaction is measured separately by PERF-10.',hidden_answer_injection=False)
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,requests=requests,native_exports=exports,
            independent_context_events=fixture.context_events,independent_events=fixture.events,independent_receipts=fixture.receipts,paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2300],metadata=metadata)
    finally:
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-3000:]
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
