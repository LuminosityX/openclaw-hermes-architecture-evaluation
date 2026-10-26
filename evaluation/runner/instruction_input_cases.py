"""Native discovery, precedence and explicit reads of owned AGENTS/Skill inputs."""
import hashlib
import json
from pathlib import Path
import shutil

import execution_authority_cases as authority
from operation_fixture import OperationFixture
import pilot

SCENARIOS={f'EXT-06-S{i:02}':name for i,name in enumerate([
    'agents-hierarchy','extra-skill','relative-resource','precedence-and-metadata'],1)}


def skill(directory,name,description,body,metadata=None):
    directory.mkdir(parents=True)
    front='---\nname: '+name+'\ndescription: '+description+'\n'
    if metadata is not None:front+='metadata: '+json.dumps(metadata)+'\n'
    (directory/'SKILL.md').write_text(front+'---\n\n'+body+'\n')
    return directory/'SKILL.md'


def configure(root,mode):
    config=authority.configure(root,'native-file')
    workspace=root/'workspace';extra=root/'extra-skills';extra.mkdir()
    (workspace/'AGENTS.md').write_text('ROOT_GUIDANCE_63b491: owned root operating instructions.\n')
    nested=workspace/'nested';nested.mkdir();(nested/'AGENTS.md').write_text('NESTED_GUIDANCE_74ca81: explicitly read nested instructions for the nested task.\n')
    # Reads are workspace-only for the authority test, but explicitly trusted
    # configured extra skills are outside that workspace. This compatibility
    # experiment grants reads to the owned extra directory, not a new sandbox.
    config['tools']['fs']['workspaceOnly']=False
    config['skills']=dict(load=dict(extraDirs=[str(extra)]))
    if mode in {'extra-skill','relative-resource'}:
        directory=extra/'evaluation-input-skill'
        skill(directory,'evaluation-input-skill','EXTRA_SKILL_DISCOVERY_81da24 owned evaluation guidance',
            'SKILL_BODY_92ed36. Read {baseDir}/references/rules.txt for the owned relative resource.')
        (directory/'references').mkdir();(directory/'references/rules.txt').write_text('RELATIVE_RESOURCE_95af18\n')
    elif mode=='precedence-and-metadata':
        skill(extra/'conflict','evaluation-conflict','LOW_PRIORITY_SKILL_13ac57','LOW_PRIORITY_BODY_21a95f')
        skill(workspace/'skills/conflict','evaluation-conflict','WORKSPACE_PRIORITY_SKILL_42a82e','WORKSPACE_PRIORITY_BODY_61c48a')
        skill(extra/'gated','evaluation-gated','GATED_SKILL_71dea2','GATED_BODY',dict(openclaw=dict(requires=dict(bins=['evaluation-absent-binary-93e27']))))
        skill(extra/'legacy','evaluation-legacy','LEGACY_METADATA_SKILL_14df25','LEGACY_BODY',dict(clawdbot=dict(requires=dict(bins=['evaluation-absent-binary-93e27']))))
    pilot.save(root/'config.json',config)
    return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];fixture=OperationFixture();gateway=None;assertions=[]
    token='PILOT_INSTRUCTIONS_'+scenario.replace('-','_')+'_U'+str(unit)
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-provider-input','native-tool-return','owned-source-manifest']))
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:configure(p,mode));gateway.ready()
        control=token+'_CONTROL';fixture.register(control);positive=gateway.request(control)
        if not positive['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Native positive control failed')
        row.update(native_invoked=True,fixture_validated=True)
        workspace=root/'workspace'
        if mode=='agents-hierarchy':
            path=workspace/'nested/AGENTS.md';expected='NESTED_GUIDANCE_74ca81'
        elif mode=='extra-skill':
            path=root/'extra-skills/evaluation-input-skill/SKILL.md';expected='SKILL_BODY_92ed36'
        elif mode=='relative-resource':
            # The first real native read obtains the skill and materialized
            # base directory; the second reads its actual relative resource.
            first=token+'_SKILL';skill_path=root/'extra-skills/evaluation-input-skill/SKILL.md'
            fixture.plan(first,'read',dict(path=str(skill_path)),'SKILL_BODY_92ed36')
            result=gateway.request(first,session_key=token.lower())
            if not result['accepted']:raise RuntimeError('Native skill-body read positive control failed')
            path=skill_path.parent/'references/rules.txt';expected='RELATIVE_RESOURCE_95af18'
        else:
            path=workspace/'skills/conflict/SKILL.md';expected='WORKSPACE_PRIORITY_BODY_61c48a'
        fixture.plan(token,'read',dict(path=str(path)),expected)
        result=gateway.request(token,session_key=token.lower() if mode=='relative-resource' else None)
        native_messages=fixture.native_inputs.get(token,[]);native_text=json.dumps(native_messages,ensure_ascii=False)
        returned=fixture.tool_returns.get(token,[])
        check('owned-instruction-resource-actually-readable',result['accepted'] and expected in json.dumps(returned))
        check('root-agents-guidance-reaches-native-model-context','ROOT_GUIDANCE_63b491' in native_text)
        metadata=dict(public_api_only=True,core_edits=0,
            compatibility_scope='Deterministic native discovery and transport only; no claim of model obedience or behavioral equivalence with another agent framework.',
            native_context_sha256=hashlib.sha256(native_text.encode()).hexdigest(),native_context_bytes=len(native_text.encode()))
        if mode=='agents-hierarchy':
            metadata['nested_guidance_automatic_before_explicit_read']='NESTED_GUIDANCE_74ca81' in native_text
            metadata['nested_scope']='Root AGENTS is documented bootstrap input. The nested AGENTS file is explicitly requested through the native read tool; automatic recursive injection is measured separately, not assumed.'
        elif mode in {'extra-skill','relative-resource'}:
            check('configured-extra-skill-discovered-in-native-roster','EXTRA_SKILL_DISCOVERY_81da24' in native_text)
            if mode=='relative-resource':
                check('skill-body-and-relative-reference-retained-in-native-session','SKILL_BODY_92ed36' in native_text and 'references/rules.txt' in native_text)
                metadata['resource_resolution']='The scripted task resolves the documented skill base directory and performs a native read; this does not claim the runtime automatically executes relative references.'
        else:
            check('workspace-skill-wins-documented-precedence','WORKSPACE_PRIORITY_SKILL_42a82e' in native_text and 'LOW_PRIORITY_SKILL_13ac57' not in native_text)
            check('new-metadata-missing-binary-gates-skill','GATED_SKILL_71dea2' not in native_text)
            check('legacy-clawdbot-metadata-does-not-apply-new-gating','LEGACY_METADATA_SKILL_14df25' in native_text)
        markers=['ROOT_GUIDANCE','NESTED_GUIDANCE','EXTRA_SKILL_DISCOVERY','WORKSPACE_PRIORITY','LOW_PRIORITY','GATED_SKILL','LEGACY_METADATA','SKILL_BODY','references/rules.txt']
        metadata['native_context_marker_presence']={marker:marker in native_text for marker in markers}
        metadata['source_sha256']={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.md')}
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,metadata=metadata,
            request={k:v for k,v in result.items() if k!='response_excerpt'},native_tool_returns=returned,
            independent_events=fixture.events,resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2500])
    finally:
        if gateway:gateway.stop()
        fixture.close();shutil.rmtree(root,ignore_errors=True)
        row['owned_state_retained']=root.exists()
    return row
