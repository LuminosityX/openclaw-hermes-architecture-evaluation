"""Real previous/current core comparison and owned extension contract evolution."""
import hashlib
import json
from pathlib import Path
import shutil

import dependency_cases as deps
from effect_recovery_cases import wait_control
from operation_fixture import OperationFixture
from package_registry_fixture import archive
import pilot
import service_path_cases as service

PLUGIN='eval-version-reference'
SCENARIOS={f'EXT-03-S{i:02}':mode for i,mode in enumerate(['old-extension','optional-field','absent-capability','startup-failure'],1)}


def reference_archive():
    package=dict(name=PLUGIN,version='1.0.0',type='module',openclaw=dict(extensions=['./index.mjs']))
    manifest=dict(id=PLUGIN,activation=dict(onStartup=True),contracts=dict(tools=['version_probe','optional_version_probe']),
        configSchema=dict(type='object',properties=dict(failStartup=dict(type='boolean')),additionalProperties=False))
    code="""export default {id:'eval-version-reference',register(api){
 if(api.pluginConfig.failStartup)throw new Error('OWNED_EXTENSION_STARTUP_FAIL');
 const tool=name=>({name,description:'Owned extension version contract',parameters:{type:'object',properties:{token:{type:'string'},note:{type:'string'}},required:['token']},
 async execute(id,args){const r=await fetch('http://127.0.0.1:18080/effect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:args.token,pid:process.pid})});
 return {content:[{type:'text',text:JSON.stringify({version:'1.0.0',note:args.note??'ABSENT',api_keys:Object.keys(api).sort(),receipt:await r.json()})}]};}});
 api.registerTool(tool('version_probe'));api.registerTool(tool('optional_version_probe'),{optional:true});
}};\n"""
    return archive({'package.json':json.dumps(package),'openclaw.plugin.json':json.dumps(manifest),'index.mjs':code})


def environment_selfcheck():
    path=Path('/previous/identity.json');identity=json.loads(path.read_text())
    expected=json.loads(Path('/previous-target.json').read_text())
    if identity.get('current_campaign_target') is not False or identity['target']['version']!=expected['version'] or identity['target']['source_commit']!=expected['source_commit']:
        raise RuntimeError('Historical comparison identity is not the explicitly pinned previous core')
    cli=Path('/previous/node_modules/openclaw/openclaw.mjs')
    if hashlib.sha256(cli.read_bytes()).hexdigest()!=identity['core_cli_sha256']:raise RuntimeError('Historical comparison executable digest changed')
    return identity


def configure(root):
    config=service.configure(root);config['tools']['allow'].append('version_probe');pilot.save(root/'config.json',config);return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];token='PILOT_VERSION_'+scenario.replace('-','_')+'_U'+str(unit)
    fixture=OperationFixture();gateway=None;commands=[];requests=[];assertions=[];metadata={};original_cli=pilot.CLI
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    artifact=reference_archive();metadata['exact_reference_archive_sha256']=hashlib.sha256(artifact).hexdigest()
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['actual-previous-and-current-native-core-invocations','identical-extension-artifact-hash','native-optional-tool-schema-and-registration-errors','independent-effects']))
    def command(directory,*arguments):result=deps.command(directory,directory/'owned-cache',*arguments);commands.append(result);return result
    def install(directory):
        configure(directory);path=directory/'immutable-reference.tgz';path.write_bytes(artifact)
        result=command(directory,'install',path,'--accept-capabilities')
        if result['returncode']:raise RuntimeError('Native reference install failed on its declared core: '+json.dumps(result)[-1300:])
        result=command(directory,'enable',PLUGIN,'--accept-capabilities')
        if result['returncode']:raise RuntimeError('Actual reference plugin enablement failed')
    def start(directory,tag):
        nonlocal gateway
        gateway=pilot.Gateway(directory,configurer=service.reuse);gateway.ready();wait_control(gateway,fixture,token+'_'+tag+'_READY')
    def probe(tag,tool='version_probe',note=None):
        item=token+'_'+tag;arguments=dict(token=item)
        if note is not None:arguments['note']=note
        fixture.plan(item,tool,arguments,'RECEIPT:'+item);result=gateway.request(item);requests.append(result);return item,result
    try:
        if mode=='old-extension':
            identity=environment_selfcheck();pilot.CLI='/previous/node_modules/openclaw/openclaw.mjs';old=root/'previous';install(old);start(old,'PREVIOUS')
            item,result=probe('PREVIOUS_ACTION')
            if not result['accepted'] or fixture.receipts.get(item)!=1:raise RuntimeError('Identical reference extension did not work on its actual previous-core positive control')
            metadata['historical_comparison_identity']=identity;metadata['previous_tool_result']=fixture.tool_returns.get(item,[])
            gateway.stop();gateway=None;pilot.CLI=original_cli
        current=root/'current';install(current);start(current,'CURRENT');item,result=probe('CURRENT_CONTROL')
        if not result['accepted'] or fixture.receipts.get(item)!=1:raise RuntimeError('Actual pinned current-core reference tool control failed')
        row.update(native_invoked=True,fixture_validated=True)
        if mode=='old-extension':
            check('identical-previous-working-extension-executes-on-pinned-current-core',result['accepted'] and fixture.receipts.get(item)==1)
            metadata['current_tool_result']=fixture.tool_returns.get(item,[])
        elif mode=='optional-field':
            absent=''.join(m.get('content','') if isinstance(m.get('content'),str) else json.dumps(m.get('content')) for m in fixture.tool_returns.get(item,[]))
            check('existing-caller-without-new-optional-field-remains-compatible','ABSENT' in absent)
            marker='OWNED_OPTIONAL_π_中文';item,result=probe('OPTIONAL_ADDED',note=marker)
            check('optional-extension-tool-field-arrives-without-contract-regression',result['accepted'] and fixture.receipts.get(item)==1 and marker in json.dumps(fixture.tool_returns.get(item,[]),ensure_ascii=False))
            metadata['optional_field_scope']='Actual extension tool input schema with an additive optional field. This does not assert that every upstream Plugin SDK version change is compatible.'
        elif mode=='absent-capability':
            item,result=probe('OPTIONAL_NOT_ENABLED',tool='optional_version_probe')
            advertised=[e for e in fixture.events if e.get('token')==item and e['kind']=='native-operation-provider-request']
            if not advertised:raise RuntimeError('Actual missing-capability catalog observation was not established')
            check('unselected-optional-plugin-capability-is-absent',not result['accepted'] and not fixture.receipts.get(item) and all('optional_version_probe' not in e['advertised_tools'] for e in advertised))
            gateway.stop();config=json.loads((current/'config.json').read_text());config['tools']['allow'].append('optional_version_probe');pilot.save(current/'config.json',config);start(current,'OPTIONAL_ENABLED')
            item,result=probe('OPTIONAL_NOW_ENABLED',tool='optional_version_probe')
            check('same-real-optional-capability-works-after-explicit-opt-in',result['accepted'] and fixture.receipts.get(item)==1)
            metadata['capability_absence_scope']='A real registered optional plugin tool is absent until explicit tool-policy opt-in. No host SDK function is deleted or fabricated as missing.'
        else:
            gateway.stop();config=json.loads((current/'config.json').read_text());config['plugins']['entries'][PLUGIN]['config']=dict(failStartup=True);pilot.save(current/'config.json',config);start(current,'STARTUP_FAULT')
            item,result=probe('STARTUP_FAILED_TOOL')
            inspected=command(current,'inspect',PLUGIN,'--runtime','--json');metadata['actual_native_failed_registration']=inspected
            diagnostic=json.dumps(inspected)+'\n'+''.join(gateway.log_tail)
            if 'OWNED_EXTENSION_STARTUP_FAIL' not in diagnostic:raise RuntimeError('Actual configured registration failure was not observed in native diagnostics')
            check('failed-extension-startup-does-not-advertise-working-tool',not result['accepted'] and not fixture.receipts.get(item))
            gateway.stop();config['plugins']['entries'][PLUGIN]['config']=dict(failStartup=False);pilot.save(current/'config.json',config);start(current,'REPAIRED')
            item,result=probe('REPAIRED_ACTION');check('corrected-plugin-configuration-restores-the-original-artifact',result['accepted'] and fixture.receipts.get(item)==1)
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,
            native_commands=commands,requests=requests,native_tool_returns=fixture.tool_returns,resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2400],metadata=metadata,native_commands=commands)
    finally:
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-4000:]
        pilot.CLI=original_cli;row.update(independent_events=fixture.events,independent_effects=fixture.receipts)
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
