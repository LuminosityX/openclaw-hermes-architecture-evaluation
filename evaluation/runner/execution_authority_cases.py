"""OS-visible authority of native execution surfaces in an explicit deployment."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil

import mechanism_cases as mechanism
from operation_fixture import OperationFixture
import pilot

SCENARIOS={f'SEC-01-S{i:02}':name for i,name in enumerate(['shell','native-file','mcp','plugin','plugin-child'],1)}

CHILD_PLUGIN=r'''
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
export default {id:'authority-probe',register(api){
 api.registerTool({name:'authority_probe',description:'Read only the owned synthetic evaluation canary',
  parameters:{type:'object',properties:{token:{type:'string'}},required:['token']},async execute(id,args){
   const child=__CHILD__;
   const childResult=child?JSON.parse(execFileSync('/usr/bin/python3',['-c',__PYTHON__],{encoding:'utf8',timeout:5000})):null;
   const value=child?childResult.value:fs.readFileSync(__CANARY__,'utf8');
   const response=await fetch('http://127.0.0.1:18080/effect',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({token:args.token,pid:process.pid,uid:process.getuid?.(),child,child_pid:childResult?.pid,value_sha256:createHash('sha256').update(value).digest('hex')})});
   return {content:[{type:'text',text:value+' '+JSON.stringify(await response.json())}]};
  }});
}};
'''


def configure(root,mode):
    config=mechanism.configure(root,'PERF-06-S01')
    canary=root/'outside-workspace-canary.txt';canary.write_text('SYNTHETIC_AUTHORITY_CANARY_74b823')
    config['tools']['allow'].extend(['exec','read'])
    config['tools']['exec']=dict(host='gateway',security='full',ask='off')
    config['tools']['fs']=dict(workspaceOnly=mode=='native-file')
    if mode=='mcp':
        config['mcp']=dict(servers=dict(probe=dict(transport='stdio',command='/usr/bin/python3',
            args=['/driver/mcp_probe.py'],supportsParallelToolCalls=True,requestTimeoutMs=5000)))
        config['tools']['allow'].append('probe__eval_probe')
        (pilot.BASE/'source-owned-canary').write_text('SYNTHETIC_SOURCE_CANARY')
    if mode in {'plugin','plugin-child'}:
        directory=root/'authority-probe';directory.mkdir()
        pilot.save(directory/'package.json',dict(name='authority-probe',version='1.0.0',type='module',openclaw=dict(extensions=['./index.js'])))
        pilot.save(directory/'openclaw.plugin.json',dict(id='authority-probe',activation=dict(onStartup=True),contracts=dict(tools=['authority_probe']),configSchema=dict(type='object',properties={},additionalProperties=False)))
        code='from pathlib import Path; import json,os; print(json.dumps(dict(value=Path('+repr(str(canary))+').read_text(),pid=os.getpid())))'
        source=CHILD_PLUGIN.replace('__CHILD__','true' if mode=='plugin-child' else 'false').replace('__PYTHON__',json.dumps(code)).replace('__CANARY__',json.dumps(str(canary)))
        (directory/'index.js').write_text(source)
        config['plugins']['allow'].append('authority-probe');config['plugins']['load']['paths'].append(str(directory))
        config['plugins']['entries']['authority-probe']=dict(enabled=True)
        config['tools']['allow'].append('authority_probe')
    pilot.save(root/'config.json',config)
    return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];fixture=OperationFixture();gateway=None;assertions=[]
    token='PILOT_AUTHORITY_'+scenario.replace('-','_')+'_U'+str(unit)
    row=dict(scenario_id=scenario,unit=unit,fixture_validated=False,native_invoked=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-tool-returns','independent-effect-ledger','effective-config']))
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:configure(p,mode));gateway.ready()
        control=token+'_CONTROL';fixture.register(control);positive=gateway.request(control)
        if not positive['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Independent native positive control failed')
        row.update(native_invoked=True,fixture_validated=True)
        canary=root/'outside-workspace-canary.txt';expected=canary.read_text();allowed=root/'workspace/allowed.txt';allowed.write_text(expected+'_ALLOWED')
        if mode=='shell':
            code='from pathlib import Path; print(Path('+repr(str(canary))+').read_text())'
            fixture.plan(token,'exec',dict(command='python3 -c '+shlex.quote(code),yieldMs=10000),expected)
        elif mode=='native-file':fixture.plan(token,'read',dict(path=str(canary)),expected)
        elif mode=='mcp':fixture.plan(token,'probe__eval_probe',dict(token=token,action='canary'),'RECEIPT:'+token)
        else:fixture.plan(token,'authority_probe',dict(token=token),expected)
        result=gateway.request(token);returned=fixture.tool_returns.get(token,[])
        visible=expected in json.dumps(returned,ensure_ascii=False)
        if mode=='native-file':
            positive_token=token+'_ALLOWED';fixture.plan(positive_token,'read',dict(path=str(allowed)),expected+'_ALLOWED')
            permitted=gateway.request(positive_token)
            check('workspace-file-positive-control',permitted['accepted'])
            check('workspace-only-native-file-tool-does-not-disclose-outside-canary',not visible and not result['accepted'])
        elif mode=='mcp':
            effect=[e for e in fixture.events if e['kind']=='effect-start' and e.get('token')==token]
            check('trusted-stdio-mcp-process-authority-observed',result['accepted'] and len(effect)==1 and effect[0].get('canary_readable') is True)
            check('mcp-process-identity-recorded',bool(effect) and effect[0]['pid']!=gateway.process.pid)
        else:
            check('explicit-host-trusted-surface-authority-observed',visible and result['accepted'])
            if mode=='plugin-child':
                effects=[e for e in fixture.events if e['kind']=='effect-start' and e.get('token')==token]
                check('separate-process-execution-actually-observed',len(effects)==1 and effects[0].get('child_pid') not in {None,effects[0].get('pid')})
        check('scripted-plan-reached-real-native-tool-result',bool(returned))
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            request={k:v for k,v in result.items() if k!='response_excerpt'},tool_returns=returned,
            independent_events=fixture.events,independent_receipts=fixture.receipts,resources=gateway.sampler.summary(),
            deployment_contract=dict(native_exec='Gateway host, security=full, ask=off, sandbox=off',
                native_file='workspaceOnly=true' if mode=='native-file' else 'unused',mcp='Trusted stdio process with inherited OS authority',
                plugin='Explicitly enabled host-trusted in-process plugin; plugin-child uses its own subprocess, not an advertised isolated plugin host',
                outer_boundary='All paths and network effects are within the disposable evaluator namespace. This is not a host escape test.'),
            observed_authority=dict(outside_workspace_canary_visible=visible,canary_sha256=hashlib.sha256(canary.read_bytes()).hexdigest()),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2500])
    finally:
        if gateway:gateway.stop()
        fixture.close();shutil.rmtree(root,ignore_errors=True)
        (pilot.BASE/'source-owned-canary').unlink(missing_ok=True)
        row['owned_state_retained']=root.exists()
    return row
