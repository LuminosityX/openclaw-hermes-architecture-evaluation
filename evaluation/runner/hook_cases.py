"""Reference hooks through public api.on; independent receipts remain authoritative."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import time

import pilot

SCENARIOS={f'EXT-08-S{i:02}':name for i,name in enumerate([
    'before-after','priority','mutation','observer-errors','async-cancel','disable-reregister'],1)}

HOOKS=r'''
  const mode=__HOOK_MODE__;
  let originalToken='';
  const log=async(name,event={},ctx={})=>{
    await fetch('http://127.0.0.1:18080/hook',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name,token:event.params?.token??originalToken,tool_name:event.toolName,
        call_id:event.toolCallId??ctx.toolCallId,run_id:event.runId??ctx.runId,
        session_key:ctx.sessionKey,signal_available:!!ctx.abortSignal})});
  };
  api.on('before_tool_call',async(event,ctx)=>{
    originalToken=event.params.token;
    await log('before-high',event,ctx);
    if(mode==='priority')return {params:{...event.params,token:event.params.token+'_HIGH'}};
    if(mode==='mutation')return {params:{...event.params,token:event.params.token+'_MUT'}};
    if(mode==='async-cancel'){
      await new Promise(resolve=>{
        const timer=setTimeout(resolve,12000);
        ctx.abortSignal?.addEventListener('abort',()=>{clearTimeout(timer);log('hook-aborted',event,ctx).finally(resolve);},{once:true});
      });
      await log('async-hook-settled',event,ctx);
      if(ctx.abortSignal?.aborted)return {block:true,blockReason:'Synthetic cancellation observed'};
    }
  },{matcher:['eval_probe'],priority:50,timeoutMs:15000});
  if(mode==='priority')api.on('before_tool_call',async(event,ctx)=>{
    await log('before-low',event,ctx);
    return {params:{...event.params,token:event.params.token+'_LOW'}};
  },{matcher:['eval_probe'],priority:10});
  api.on('after_tool_call',async(event,ctx)=>{
    await log('after',event,ctx);
    if(mode==='observer-errors'){
      if(originalToken.includes('_HOOKTHROW_'))throw new Error('EVAL_AFTER_OBSERVER_THROW');
      await new Promise(resolve=>setTimeout(resolve,400));
      await log('late-observer-settled',event,ctx);
    }
    if(mode==='mutation')return {result:{content:[{type:'text',text:'AFTER_OBSERVER_RETURN_MUST_BE_IGNORED'}]}};
  },{matcher:['eval_probe'],timeoutMs:mode==='observer-errors'?100:5000});
  if(mode==='mutation')api.on('tool_result_persist',(event,ctx)=>{
    const serialized=JSON.stringify(event.message);
    if(!serialized.includes('_MUT'))return;
    return {message:JSON.parse(serialized.replaceAll('_MUT','_PERSISTED'))};
  });
'''


class HookFixture(pilot.Fixture):
    def handler(self):
        base=super().handler()
        owner=self
        class Handler(base):
            def do_POST(self):
                if self.path!='/hook': return super().do_POST()
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=16384: return self.send({'error':'bounded hook fixture'},413)
                data=json.loads(self.rfile.read(size))
                owner.event('hook',**data)
                return self.send({'observed':True})
        return Handler


def configure(root,scenario):
    hooks=HOOKS.replace('__HOOK_MODE__',json.dumps(SCENARIOS[scenario]))
    return pilot.configuration(root,tool_search=False,plugin_registration=hooks)


def rpc(gateway,method,params):
    env=dict(os.environ,OPENCLAW_STATE_DIR=str(gateway.root/'state'),OPENCLAW_CONFIG_PATH=str(gateway.root/'config.json'),
             OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_DISABLE_BUNDLED_PLUGINS='1')
    result=subprocess.run([pilot.NODE,pilot.CLI,'gateway','call',method,'--params',json.dumps(params),'--json'],
                          env=env,capture_output=True,text=True,timeout=25)
    return dict(returncode=result.returncode,stdout=result.stdout[-3000:],stderr=result.stderr[-1000:])


def run_requests(gateway,fixture,scenario,token):
    mode=SCENARIOS[scenario]
    if mode=='observer-errors':
        requests=[gateway.request(token+'_HOOKTHROW_'),gateway.request(token+'_HOOKTIMEOUT_')]
        time.sleep(.6)
        return requests,{},gateway
    if mode=='async-cancel':
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(gateway.request,token)
            until=time.monotonic()+20
            while time.monotonic()<until:
                if any(e['kind']=='hook' and e.get('name')=='before-high' and e.get('token')==token for e in fixture.events): break
                if future.done(): break
                time.sleep(.05)
            cancellation=rpc(gateway,'sessions.abort',{'key':'agent:main:pilot:'+token.lower()})
            request=future.result(timeout=40)
        time.sleep(.2)
        return [request],dict(cancellation=cancellation),gateway
    if mode=='disable-reregister':
        initial=gateway.request(token+'_INITIAL_')
        gateway.stop()
        config=gateway.config
        config['plugins']['entries']['pilot-probe']['enabled']=False
        pilot.save(gateway.root/'config.json',config)
        disabled=pilot.Gateway(gateway.root,configurer=lambda _:config)
        try: disabled.ready()
        except Exception:
            disabled.stop()
            raise
        denied=disabled.request(token+'_DISABLED_')
        disabled.stop()
        config['plugins']['entries']['pilot-probe']['enabled']=True
        pilot.save(gateway.root/'config.json',config)
        enabled=pilot.Gateway(gateway.root,configurer=lambda _:config)
        try: enabled.ready()
        except Exception:
            enabled.stop()
            raise
        final=enabled.request(token+'_REENABLED_')
        return [initial,denied,final],dict(lifecycle='Disable and re-register across explicit native Gateway restarts; not a hot-reload race'),enabled
    return [gateway.request(token)],{},gateway


def acceptance(scenario,requests,events,metadata):
    mode=SCENARIOS[scenario]
    checks=[]
    hooks=[e for e in events if e['kind']=='hook']
    effects=[e for e in events if e['kind']=='effect-commit']
    def check(name,value): checks.append(dict(name=name,verdict='pass' if value else 'fail',evidence=['native-request','independent-events']))
    check('native-tool-hook-exercised',bool(hooks))
    if mode=='async-cancel':
        check('cancellation-rpc-accepted',metadata['cancellation']['returncode']==0)
        check('no-effect-after-cancellation',not effects)
        check('no-false-completion',not requests[0]['accepted'])
        check('async-hook-settled',any(e.get('name')=='async-hook-settled' for e in hooks))
    elif mode=='disable-reregister':
        check('enabled-and-reenabled-complete',requests[0]['accepted'] and requests[2]['accepted'])
        check('disabled-plugin-no-effect',not any('_DISABLED_' in e.get('token','') for e in effects))
        check('one-before-hook-per-enabled-call',sum(e.get('name')=='before-high' for e in hooks)==2)
    else:
        check('all-native-tasks-complete',all(r['accepted'] for r in requests))
        check('one-effect-per-task',len(effects)==len(requests))
    if mode=='before-after':
        before=[e for e in hooks if e.get('name')=='before-high']
        after=[e for e in hooks if e.get('name')=='after']
        starts=[e for e in events if e['kind']=='effect-start']
        check('exactly-one-before-and-after',len(before)==len(after)==1)
        check('before-effect-after-order',bool(before and after and starts and effects) and before[0]['monotonic_ns']<starts[0]['monotonic_ns']<effects[0]['monotonic_ns']<after[0]['monotonic_ns'])
    if mode=='priority':
        before=[e for e in hooks if e.get('name','').startswith('before-')]
        check('priority-order',[e['name'] for e in before]==['before-high','before-low'])
        check('isolated-original-parameter-copies',len(before)==2 and before[0]['token']==before[1]['token'])
        check('last-returned-parameters-win',len(effects)==1 and effects[0]['token'].endswith('_LOW'))
    if mode=='mutation':
        replay=[e for e in events if e['kind']=='tool-result']
        check('input-rewrite-reaches-tool',len(effects)==1 and effects[0]['token'].endswith('_MUT'))
        check('persistence-rewrite-reaches-native-transcript',metadata.get('persisted_receipt_visible') is True)
        check('after-observer-return-ignored',not any('AFTER_OBSERVER_RETURN_MUST_BE_IGNORED' in e.get('excerpt','') for e in replay))
    if mode=='observer-errors':
        check('throw-and-timeout-both-exercised',len([e for e in hooks if e.get('name')=='after'])==2)
        check('timed-out-work-retained-in-evidence',any(e.get('name')=='late-observer-settled' for e in hooks))
    return checks
