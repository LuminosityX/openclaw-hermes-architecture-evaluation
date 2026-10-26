"""Declared external artifact corpus with actual native compatibility probes."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import dependency_cases as deps
from effect_recovery_cases import wait_control
import harness_contract_cases as harness
from operation_fixture import OperationFixture
from package_registry_fixture import archive
import pilot
import service_path_cases as service

PLUGIN='eval-external-corpus'
SCENARIOS={f'EXT-07-S{i:02}':mode for i,mode in enumerate(['mcp-config','foreign-sdk','external-harness','update-uninstall'],1)}


def native_archive(version):
    package=dict(name=PLUGIN,version=version,type='module',openclaw=dict(extensions=['./index.mjs']))
    manifest=dict(id=PLUGIN,activation=dict(onStartup=True),contracts=dict(tools=['external_corpus_probe']),configSchema=dict(type='object',properties={},additionalProperties=False))
    code="export default {id:"+json.dumps(PLUGIN)+",register(api){api.registerTool({name:'external_corpus_probe',description:'Owned corpus lifecycle probe',parameters:{type:'object',properties:{token:{type:'string'}},required:['token']},async execute(id,args){const r=await fetch('http://127.0.0.1:18080/effect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:args.token,pid:process.pid})});return {content:[{type:'text',text:'VERSION:"+version+" '+JSON.stringify(await r.json())}]};}});}};\n"
    return archive({'package.json':json.dumps(package),'openclaw.plugin.json':json.dumps(manifest),'index.mjs':code})


def foreign_archive():
    package=dict(name='owned-foreign-vscode-corpus',version='1.0.0',publisher='owned-evaluation',engines=dict(vscode='^1.90.0'),main='./extension.cjs',
        activationEvents=['onCommand:ownedCorpus.add'],contributes=dict(commands=[dict(command='ownedCorpus.add',title='Owned bounded arithmetic')]))
    source="const vscode=require('vscode');exports.activate=context=>{context.subscriptions.push(vscode.commands.registerCommand('ownedCorpus.add',(left,right)=>left+right));};exports.deactivate=()=>{};\n"
    return archive({'package.json':json.dumps(package),'extension.cjs':source})


def configure(root):
    config=service.configure(root);config['tools']['allow'].append('external_corpus_probe');pilot.save(root/'config.json',config);return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario]
    if mode in {'mcp-config','external-harness'}:
        mapping=[];artifact={}
        def mcp_import(path):
            config=service.configure(path);config['tools']['allow'].append('external__eval_probe');pilot.save(path/'config.json',config)
            definition=dict(command='/usr/bin/python3',args=['/driver/external_harness_worker.py'])
            raw=json.dumps(dict(mcpServers=dict(external=definition)),sort_keys=True).encode()
            artifact.update(format='mcpServers JSON',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
            env=dict(os.environ,OPENCLAW_STATE_DIR=str(path/'state'),OPENCLAW_CONFIG_PATH=str(path/'config.json'),OPENCLAW_DISABLE_BUNDLED_PLUGINS='1')
            result=subprocess.run([pilot.NODE,pilot.CLI,'mcp','set','external',json.dumps(definition)],env=env,capture_output=True,text=True,timeout=40)
            mapping.append(dict(returncode=result.returncode,stdout=result.stdout[-2500:],stderr=result.stderr[-1500:]))
            if result.returncode:raise RuntimeError('Actual native MCP server-definition import failed')
            return json.loads((path/'config.json').read_text())
        row=harness.run_scenario(root,'EXT-02-S01' if mode=='mcp-config' else 'EXT-02-S03',unit,configurer=mcp_import if mode=='mcp-config' else None)
        row['scenario_id']=scenario
        row.setdefault('metadata',{}).update(corpus_mode=mode,compatibility='documented-config-mapping' if mode=='mcp-config' else 'documented-public-harness-adapter',
            original_config_artifact=artifact,native_import_commands=mapping,
            corpus_scope='A fresh native execution of the declared owned reference corpus. Reuses the tested integration mechanism, never reuses or promotes earlier observations. MCP is a callable tool; the full harness has separate actual runAttempt and transcript evidence.')
        return row
    fixture=OperationFixture();gateway=None;commands=[];requests=[];assertions=[];metadata={};cache=root/'owned-cache'
    token='PILOT_EXTERNAL_CORPUS_'+scenario.replace('-','_')+'_U'+str(unit)
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['actual-native-installer-and-runtime-results','declared-artifact-corpus-hashes','independent-tool-effects-and-install-policy']))
    def command(*arguments):result=deps.command(root,cache,*arguments);commands.append(result);return result
    def restart(tag):
        nonlocal gateway
        if gateway:gateway.stop()
        gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready();wait_control(gateway,fixture,token+'_'+tag+'_READY')
    def probe(tag,version):
        item=token+'_'+tag;fixture.plan(item,'external_corpus_probe',dict(token=item),'VERSION:'+version)
        result=gateway.request(item);requests.append(result);return item,result
    try:
        configure(root);original=native_archive('1.0.0');path=root/'native-corpus.tgz';path.write_bytes(original)
        metadata['native_v1_archive_sha256']=hashlib.sha256(original).hexdigest()
        installed=command('install',path,'--accept-capabilities')
        if installed['returncode']:raise RuntimeError('Actual native dependency-free corpus install positive control failed: '+json.dumps(installed)[-1500:])
        enabled=command('enable',PLUGIN,'--accept-capabilities')
        if enabled['returncode']:raise RuntimeError('Native installed corpus enablement failed')
        restart('BASELINE');control,positive=probe('V1_CONTROL','1.0.0')
        if not positive['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Actual installed native corpus tool positive control failed')
        row.update(native_invoked=True,fixture_validated=True);gateway.stop()
        if mode=='foreign-sdk':
            data=foreign_archive();foreign=root/'foreign-sdk.tgz';foreign.write_bytes(data)
            metadata.update(foreign_artifact_sha256=hashlib.sha256(data).hexdigest(),foreign_format='Owned VS Code command extension package using the documented vscode activate(context) SDK',
                foreign_host_scope='Manifest and entry follow the published VS Code SDK. No VS Code host installation or universal claim about all foreign plugin formats is made.')
            result=command('install',foreign,'--accept-capabilities');diagnostic=result['stdout']+'\n'+result['stderr']
            if result['returncode']==0:raise RuntimeError('Foreign SDK package was accepted; actual runnable native integration needs investigation before classifying compatibility')
            if not re.search(r'openclaw\.extensions|plugin manifest|supported bundle|missing.*extensions|no.*plugin.*found',diagnostic,re.I):
                raise RuntimeError('Foreign install failed without a proven native host-contract mismatch: '+diagnostic[-1500:])
            metadata.update(compatibility='unsupported-direct-foreign-sdk',documented_adapter='The existing stdio MCP/public harness corpus demonstrates explicit adapters; this VS Code activation entry is not silently rewritten into either one.')
            restart('AFTER_FOREIGN_REJECTION');item,result=probe('NATIVE_STILL_WORKS','1.0.0')
            check('foreign-host-contract-mismatch-is-explicitly-rejected',True)
            check('foreign-rejection-preserves-installed-native-extension',result['accepted'] and fixture.receipts.get(item)==1)
        else:
            changed=native_archive('2.0.0');path.write_bytes(changed);metadata['native_v2_archive_sha256']=hashlib.sha256(changed).hexdigest()
            metadata['native_tracked_update_probe']=command('update',PLUGIN)
            replaced=command('install',path,'--accept-capabilities')
            if replaced['returncode']:raise RuntimeError('Documented native local-archive replacement failed before its lifecycle could be observed')
            metadata.update(update_path='Native tracked update result is recorded separately; local archive v2 is explicitly replaced through plugins install --force, not mislabeled as an automatic registry update.',compatibility='native-plugin-lifecycle')
            restart('V2');item,result=probe('V2_ACTION','2.0.0')
            check('same-native-tool-executes-actual-updated-version',result['accepted'] and fixture.receipts.get(item)==1 and 'VERSION:2.0.0' in json.dumps(fixture.tool_returns.get(item,[])))
            gateway.stop();removed=command('uninstall',PLUGIN,'--force')
            check('native-uninstall-succeeds',removed['returncode']==0)
            metadata['post_uninstall_entry']=json.loads((root/'config.json').read_text())['plugins']['entries'].get(PLUGIN)
            restart('UNINSTALLED');item,result=probe('AFTER_UNINSTALL','2.0.0')
            check('uninstalled-extension-cannot-dispatch',not result['accepted'] and not fixture.receipts.get(item))
            check('native-uninstall-retains-explicit-disable-marker',metadata['post_uninstall_entry']==dict(enabled=False))
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,
            native_commands=commands,requests=requests,native_tool_returns=fixture.tool_returns,resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2400],metadata=metadata,native_commands=commands)
    finally:
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-3500:]
        row.update(independent_events=fixture.events,independent_effects=fixture.receipts)
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
