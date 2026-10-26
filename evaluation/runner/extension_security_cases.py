"""Owned extension scripts, actual authority, consent changes and disabled dispatch."""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

import dependency_cases as deps
from effect_recovery_cases import wait_control
from operation_fixture import OperationFixture
from package_registry_fixture import PackageRegistry,PLUGIN,archive,plugin_archive
import pilot
import service_path_cases as service

SCENARIOS={f'SEC-12-S{i:02}':mode for i,mode in enumerate(['script','secret','consent','substitution','disabled'],1)}


def variant(mode,root):
    with tarfile.open(fileobj=io.BytesIO(plugin_archive()),mode='r:gz') as source:
        files={p.name.removeprefix('package/'):source.extractfile(p).read().decode() for p in source.getmembers() if p.isfile()}
    package=json.loads(files['package.json']);package['version']='2.0.0'
    manifest=json.loads(files['openclaw.plugin.json']);extra=''
    if mode=='script':
        package['scripts']=dict(postinstall='node postinstall.js '+json.dumps(str(root/'install-script-effect')))
        files['postinstall.js']="import fs from 'node:fs';fs.writeFileSync(process.argv[2],'OWNED_INSTALL_SCRIPT_EXECUTED');\n"
    else:
        name='secret_probe' if mode=='secret' else 'capability_probe';manifest['contracts']['tools'].append(name)
        body=("let secret='';try{secret=fs.readFileSync("+json.dumps(str(root/'outside-workspace-secret'))+",'utf8');}catch(error){secret='OWNED_SECRET_READ_DENIED';}\n") if mode=='secret' else "const secret='OWNED_CAPABILITY_V2';\n"
        extra="api.registerTool({name:"+json.dumps(name)+",description:'Owned extension authority probe',parameters:{type:'object',properties:{token:{type:'string'}},required:['token']},async execute(id,args){"+body+"const r=await fetch('http://127.0.0.1:18080/effect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:args.token})});return {content:[{type:'text',text:secret+' '+JSON.stringify(await r.json())}]};}});\n"
        source=files['index.js'];at=source.rfind('}};');files['index.js']=("import fs from 'node:fs';\n" if mode=='secret' else '')+source[:at]+extra+source[at:]
    files['package.json']=json.dumps(package);files['openclaw.plugin.json']=json.dumps(manifest)
    return archive(files),files.get('postinstall.js')


def configure(root):
    config=deps.configure(root);config['tools']['allow'].extend(['read','secret_probe','capability_probe']);config['tools']['fs']=dict(workspaceOnly=True)
    pilot.save(root/'config.json',config);return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario]
    if mode=='substitution':return deps.run_scenario(root,scenario,unit,mode_override='substitution')
    token='PILOT_EXTENSION_SECURITY_'+scenario.replace('-','_')+'_U'+str(unit)
    canary='OwnedExtensionCanary'+hashlib.sha256(token.encode()).hexdigest()[:24]
    registry=PackageRegistry();fixture=OperationFixture();gateway=None;assertions=[];commands=[];metadata={};requests=[]
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-install-enable-disable-and-inspect','actual-native-extension-tool-returns','independent-owned-script-file-and-effect-ledger','declared-capability-consent']))
    def restart(tag):
        nonlocal gateway
        if gateway:gateway.stop()
        gateway=pilot.Gateway(root,configurer=service.reuse);gateway.ready()
        requests.extend(wait_control(gateway,fixture,token+'_'+tag+'_CONTROL'))
    def probe(tag,tool,expected=None):
        item=token+'_'+tag;fixture.plan(item,tool,dict(token=item),'RECEIPT:'+item if expected is None else expected)
        result=gateway.request(item);requests.append(result);return item,result
    def install(path,accept=True):
        arguments=['install',path]
        if accept:arguments.append('--accept-capabilities')
        result=deps.command(root,cache,*arguments);commands.append(result);return result
    try:
        configure(root);cache=root/'owned-npm-cache';base=root/'reference-v1.tgz';base.write_bytes(plugin_archive())
        first=install(base)
        if first['returncode'] or not deps.installed(deps.inspect(root,cache)):raise RuntimeError('Native reference extension installation positive control failed')
        enabled=deps.command(root,cache,'enable',PLUGIN,'--accept-capabilities');commands.append(enabled)
        if enabled['returncode']:raise RuntimeError('Native reference extension enablement failed')
        restart('BASELINE');control,positive=probe('DEPENDENCY_CONTROL','dependency_probe')
        if not positive['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Actual installed reference extension control failed')
        row.update(native_invoked=True,fixture_validated=True)
        gateway.stop()
        if mode=='disabled':
            disabled=deps.command(root,cache,'disable',PLUGIN);commands.append(disabled)
            if disabled['returncode']:raise RuntimeError('Native disable command was not accepted')
            metadata['disabled_inspection']=deps.inspect(root,cache);restart('DISABLED')
            item,result=probe('DISABLED_ATTEMPT','dependency_probe')
            check('disabled-extension-cannot-dispatch',not result['accepted'] and fixture.receipts.get(item,0)==0)
            gateway.stop();enabled=deps.command(root,cache,'enable',PLUGIN,'--accept-capabilities');commands.append(enabled)
            if enabled['returncode']:raise RuntimeError('Native re-enable control failed')
            restart('REENABLED');item,result=probe('REENABLED_ATTEMPT','dependency_probe')
            check('explicitly-reenabled-extension-dispatches-once',result['accepted'] and fixture.receipts.get(item)==1)
        else:
            data,script=variant(mode,root);target=root/'owned-v2.tgz';target.write_bytes(data)
            metadata['intervention_archive_sha256']=hashlib.sha256(data).hexdigest()
            if mode=='script':
                path=root/'script-positive-control.js';path.write_text(script);control=root/'script-control-effect'
                execution=subprocess.run([pilot.NODE,str(path),str(control)],capture_output=True,text=True,timeout=5)
                if execution.returncode or not control.is_file():raise RuntimeError('The owned postinstall script did not work in its isolated direct positive control')
                metadata['script_control_sha256']=hashlib.sha256(control.read_bytes()).hexdigest();control.unlink()
            if mode=='secret':(root/'outside-workspace-secret').write_text(canary)
            before=json.loads((root/'config.json').read_text())['plugins']['entries'].get(PLUGIN)
            changed=install(target,accept=mode!='consent');metadata['updated_inspection']=deps.inspect(root,cache)
            after=json.loads((root/'config.json').read_text())['plugins']['entries'].get(PLUGIN)
            metadata.update(native_entry_before=before,native_entry_after=after,update_without_capability_acceptance=mode=='consent')
            if mode=='script':
                effect=root/'install-script-effect';metadata.update(install_script_executed=effect.exists(),install_returncode=changed['returncode'],
                    scope='Actual native managed local-archive install/update phase. Source confirmation is explicit; script execution is measured, not inferred from package metadata.')
                check('package-postinstall-not-executed-by-default-native-install',not effect.exists())
            elif mode=='secret':
                if changed['returncode']:
                    if not re.search(r'policy|capabilit|denied|unsafe|block|security',changed['stderr']+changed['stdout'],re.I):raise RuntimeError('Secret-reading extension failed for an unclassified setup reason')
                    metadata.update(extension_code_admitted=False,synthetic_secret_disclosed=False,installation_rejection=changed)
                    restart('SECRET_REFUSED');item,result=probe('REFUSED_EXTENSION_READ','secret_probe')
                    check('rejected-extension-has-no-secret-tool-effect',not result['accepted'] and fixture.receipts.get(item,0)==0)
                else:
                    restart('SECRET_ADMITTED');item,result=probe('EXTENSION_READ','secret_probe')
                    if not fixture.tool_returns.get(item):raise RuntimeError('Admitted secret probe produced no actual native tool return')
                    metadata.update(extension_code_admitted=True,synthetic_secret_disclosed=canary in json.dumps(fixture.tool_returns[item]),native_secret_tool_return=fixture.tool_returns[item])
                    core=token+'_CORE_READ';fixture.plan(core,'read',dict(path=str(root/'outside-workspace-secret')),canary)
                    core_result=gateway.request(core);requests.append(core_result)
                    check('native-workspace-file-policy-has-a-negative-control',not core_result['accepted'] and canary not in json.dumps(fixture.tool_returns.get(core,[])))
                    check('admitted-extension-actual-authority-measured',result['accepted'] and fixture.receipts.get(item)==1)
                metadata['authority_scope']='Only synthetic text is read. Agent filesystem tools are explicitly workspaceOnly; ordinary approved plugin JavaScript executes with its native process authority. Secret access by that code is reported as actual authority, without inventing a plugin sandbox promise.'
            else:
                restart('CHANGED_CAPABILITIES');item,result=probe('BEFORE_NEW_CONSENT','capability_probe')
                metadata['post_update_pre_consent_effects']=fixture.receipts.get(item,0)
                check('new-capability-not-executed-without-new-consent',not result['accepted'] and fixture.receipts.get(item,0)==0)
                gateway.stop()
                # Explicit later consent is a separate positive control, never a
                # retrospective permission for the preceding dispatch attempt.
                accepted=install(target,accept=True)
                if accepted['returncode']:raise RuntimeError('Explicitly consented updated extension could not be installed')
                enabled=deps.command(root,cache,'enable',PLUGIN,'--accept-capabilities');commands.append(enabled)
                if enabled['returncode']:raise RuntimeError('Explicit capability acceptance enablement failed')
                restart('NEW_CONSENT');item,result=probe('AFTER_NEW_CONSENT','capability_probe')
                if not result['accepted'] or fixture.receipts.get(item)!=1:raise RuntimeError('New capability positive control failed after explicit consent')
                check('explicit-new-consent-enables-the-actual-capability',True)
        metadata.update(mode=mode,native_core_patched=False,real_secret_used=False,unknown_malware_used=False)
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,commands=commands,requests=requests,
            independent_registry_events=registry.events,independent_events=fixture.events,independent_receipts=fixture.receipts,
            resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2200],metadata=metadata,commands=commands)
    finally:
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-3000:]
        registry.close();fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
