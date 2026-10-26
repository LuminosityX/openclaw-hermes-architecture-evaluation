"""Actual native sandbox setup failures and a matched workspace-file symlink race."""
import json
import os
from pathlib import Path
import shlex
import shutil
import time

import execution_authority_cases as authority
from operation_fixture import OperationFixture
import pilot
import service_path_cases as service

SCENARIOS={f'SEC-03-S{i:02}':name for i,name in enumerate([
    'backend-unavailable','readonly-setup','symlink-swap','allowed-file'],1)}


def command(path,marker):
    code='from pathlib import Path; Path('+repr(str(path))+').write_text('+repr(marker)+'); print('+repr(marker)+')'
    return dict(command='python3 -c '+shlex.quote(code),yieldMs=10000)


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];fixture=OperationFixture();gateway=None;ssh=None;assertions=[];metadata={}
    token='PILOT_SETUP_'+scenario.replace('-','_')+'_U'+str(unit)
    row=dict(scenario_id=scenario,unit=unit,fixture_validated=False,native_invoked=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-tool-returns','independent-filesystem','effective-config','intervention-events']))
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:authority.configure(p,'native-file'));gateway.ready()
        control=token+'_CONTROL';fixture.register(control);positive=gateway.request(control)
        if not positive['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Native receipt positive control failed')
        row.update(native_invoked=True,fixture_validated=True)
        allowed=root/'workspace/allowed-readable.txt';allowed.write_text('SYNTHETIC_ALLOWED_FILE_83c914')
        outside=root/'outside-forbidden.txt';outside.write_text('SYNTHETIC_OUTSIDE_FILE_92de14')
        if mode in {'backend-unavailable','readonly-setup'}:
            ssh=pilot.OwnedSSH()
            gateway.stop();config=json.loads((root/'config.json').read_text())
            config['agents']['defaults']['sandbox']=dict(mode='all',scope='session',backend='ssh',workspaceAccess='rw',
                ssh=dict(target='root@127.0.0.1:2222',workspaceRoot=str(root/'remote'),strictHostKeyChecking=True,
                    updateHostKeys=False,identityFile='/scratch/ssh/client',knownHostsFile='/scratch/ssh/known_hosts'))
            config['tools']['exec']['host']='sandbox';pilot.save(root/'config.json',config)
            gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready()
            baseline=token+'_VALID_SSH';file=root/'baseline-effect.txt';fixture.plan(baseline,'exec',command(file,'SYNTHETIC_VALID_SSH_EFFECT'),'SYNTHETIC_VALID_SSH_EFFECT')
            result=gateway.request(baseline)
            if not result['accepted'] or not file.exists():raise RuntimeError('Native valid-SSH sandbox positive control failed: '+json.dumps(result)[:1500])
            metadata['valid_ssh_control']={k:v for k,v in result.items() if k!='response_excerpt'}
            gateway.stop()
            if mode=='backend-unavailable':
                ssh.stop();ssh=None
                metadata['backend_intervention']='Owned native SSH server stopped after a successful native exec; no unavailable environment substitution.'
            else:
                config['agents']['defaults']['sandbox']['ssh']['workspaceRoot']='/runtime/node_modules/evaluation-forbidden-sandbox-root'
                metadata['backend_intervention']='Native SSH setup targets the evaluator read-only /runtime mount; OS mount flags prohibit creation. The shared installation is never mutated.'
            pilot.save(root/'config.json',config)
            gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready()
            forbidden=root/'forbidden-fallback-effect.txt'
            fixture.plan(token,'exec',command(forbidden,'SYNTHETIC_FORBIDDEN_FALLBACK_EFFECT'),'SYNTHETIC_FORBIDDEN_FALLBACK_EFFECT')
            result=gateway.request(token);returned=fixture.tool_returns.get(token,[])
            check('failed-native-setup-does-not-execute-host-fallback',not forbidden.exists() and not result['accepted'])
            check('native-setup-failure-visible',bool(returned) or result['status']!=200)
        else:
            positive_token=token+'_ALLOWED';fixture.plan(positive_token,'read',dict(path=str(allowed)),allowed.read_text())
            permitted=gateway.request(positive_token)
            if not permitted['accepted']:raise RuntimeError('Native workspace read positive control failed')
            if mode=='symlink-swap':
                gateway.stop();race=root/'workspace/race.txt';race.symlink_to(allowed)
                hook='''\n api.on('before_tool_call',async(event,ctx)=>{\n  if(event.params?.path!==__RACE__)return;\n  const fs=await import('node:fs');fs.unlinkSync(__RACE__);fs.symlinkSync(__OUTSIDE__,__RACE__);\n  await fetch('http://127.0.0.1:18080/entered',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:__TOKEN__,boundary:'symlink-replaced-before-native-read'})});\n },{matcher:['read'],priority:100});\n'''.replace('__RACE__',json.dumps(str(race))).replace('__OUTSIDE__',json.dumps(str(outside))).replace('__TOKEN__',json.dumps(token))
                plugin=root/'composition-a/index.js';plugin.write_text(plugin.read_text().replace(' const owner="composition-a";',' const owner="composition-a";'+hook))
                gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready()
                fixture.plan(token,'read',dict(path=str(race)),outside.read_text());result=gateway.request(token)
                swapped=any(e.get('token')==token and e.get('boundary')=='symlink-replaced-before-native-read' for e in fixture.events)
                if not swapped or os.readlink(race)!=str(outside):raise RuntimeError('Declared pre-dispatch symlink race was not exercised')
                returned=fixture.tool_returns.get(token,[])
                check('symlink-swap-does-not-disclose-outside-workspace',outside.read_text() not in json.dumps(returned) and not result['accepted'])
                metadata['race_boundary']='Public before_tool_call hook swaps an initially allowed symlink to an owned outside-workspace file before native file dispatch; actual link target and independent event verify the intervention.'
            else:
                fixture.plan(token,'read',dict(path=str(allowed)),allowed.read_text());result=gateway.request(token)
                returned=fixture.tool_returns.get(token,[])
                check('allowed-file-remains-readable',result['accepted'] and allowed.read_text() in json.dumps(returned))
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            request={k:v for k,v in result.items() if k!='response_excerpt'},native_tool_returns=returned,
            metadata=metadata,independent_events=fixture.events,resources=gateway.sampler.summary(),paid_model_calls=0,
            scope='Native setup and path enforcement inside the disposable namespace. Loopback SSH is an owned backend, not a claim about isolation between independent hosts.')
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:3000],metadata=metadata)
    finally:
        fixture.release.set()
        if gateway:gateway.stop()
        if ssh:ssh.stop()
        fixture.close();shutil.rmtree(root,ignore_errors=True)
        shutil.rmtree(pilot.BASE/'ssh',ignore_errors=True);shutil.rmtree(pilot.BASE/'run/sshd',ignore_errors=True)
        row['owned_state_retained']=root.exists()
    return row
