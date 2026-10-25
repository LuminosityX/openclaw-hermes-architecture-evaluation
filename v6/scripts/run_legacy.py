"""Validated persisted deny policies: legacy OpenClaw fields and unchanged prior Hermes contract."""
import hashlib,json,os,urllib.request,subprocess
from pathlib import Path
from runtime import R,OLD,save,sandbox
from run_native_suite import M
from run_state_ops import cli
from native_provider_support import install_deepseek
from controlled import Plan

def main():
 from run_child_manual_resume import main as native_child_standard_resume
 native_child_standard_resume()
 os.chdir(OLD);results=[]
 url='https://raw.githubusercontent.com/NousResearch/hermes-agent/4d04303818b61bf3aa09278af48356315515965b/website/docs/user-guide/security.md'
 source=R/'evidence/hermes-v0.22.4-security-contract.txt'
 if not source.exists():
  with urllib.request.urlopen(url,timeout=30) as response:source.write_bytes(response.read())
 text=source.read_text()
 if 'approvals.deny' not in text:raise RuntimeError('Prior Hermes deny-policy contract not established')
 original_setup=M.setup
 def setup_with_documented_migration(run,family,kind):
  original_setup(run,family,kind)
  if family=='openclaw' and kind=='deny-legacy-migrated':
   diagnostic=run/'doctor-metadata-relay';diagnostic.mkdir();relay=Plan(diagnostic,family)
   try:
    install_deepseek(run,relay);before=json.loads((run/'state/openclaw.json').read_text());cmd=sandbox(run/'state',run/'workspace',family,cli(family,['doctor','--fix','--non-interactive']),relay.socket_dir)
    with (run/'doctor.stdout.log').open('w') as out,(run/'doctor.stderr.log').open('w') as err:p=__import__('subprocess').run(cmd,stdout=out,stderr=err,stdin=subprocess.DEVNULL,timeout=120)
    after=json.loads((run/'state/openclaw.json').read_text());save(run/'documented-migration.json',dict(command=cmd,exit_code=p.returncode,stdout=(run/'doctor.stdout.log').read_text(),stderr=(run/'doctor.stderr.log').read_text(),before=before.get('tools',{}).get('exec'),after=after.get('tools',{}).get('exec'),dependency_preparation='Pinned official DeepSeek provider artifact verified and installed through native CLI before offline Doctor; exact legacy policy restored before migration.'))
   finally:relay.close()
   if after.get('tools',{}).get('exec',{}).get('mode')!='deny':raise RuntimeError('Documented legacy-policy migration did not establish canonical deny; inspect before interpreting execution')
 M.setup=setup_with_documented_migration
 for unit in range(1,4):
  root=R/'native-legacy'/f'u{unit}';(root/'evidence').mkdir(parents=True,exist_ok=True);M.R=root;p=root/'runs-mechanisms/deny-legacy/openclaw/result.json'
  oc=json.loads(p.read_text()) if p.exists() else M.run_one('openclaw','deny-legacy');ref=R/'native-units'/f'u{unit}'/'runs-mechanisms/deny/hermes/result.json'
  if not ref.exists():raise RuntimeError('Run canonical independent Hermes deny controls first')
  h=json.loads(ref.read_text());validation=json.loads((p.parent/'config-validation.json').read_text());record=dict(unit=unit,requirement='A supported persisted explicit deny policy must retain deny semantics on the tested version.',openclaw=dict(policy={'tools':{'exec':{'security':'deny','ask':'off'}}},official_config_validation_exit=validation['exit_code'],actual=oc,evidence=str(p.relative_to(R))),hermes=dict(policy={'approvals':{'mode':'off','deny':['*']}},current_native_actual=h,evidence=str(ref.relative_to(R)),prior_contract_source=url,prior_contract_sha256=hashlib.sha256(source.read_bytes()).hexdigest()),notes='Hermes fields already documented on previous stable v0.22.4. The products need not use identical key names. A legacy semantic failure does not imply canonical modern exec.mode=deny fails, and does not imply the product is generally unusable.')
  migrated_path=root/'runs-mechanisms/deny-legacy-migrated/openclaw/result.json';migrated=json.loads(migrated_path.read_text()) if migrated_path.exists() else M.run_one('openclaw','deny-legacy-migrated');record['openclaw']['after_documented_doctor_migration']=migrated;record['notes']+=' Current locked docs require doctor --fix for saved legacy pairs; the unmigrated observation alone cannot establish failure of the supported migration path or modern deny policy.'
  results.append(record);save(R/'results/legacy-policy-semantics.json',results);print('LEGACY_DENY',unit,'OC_unmigrated_effect',oc['side_effect_created'],'OC_migrated_effect',migrated['side_effect_created'],'H_effect',h['side_effect_created'],'OC_validation_exit',validation['exit_code'],flush=True)
 print('LEGACY_POLICY_COMPLETE',len(results),flush=True)
if __name__=='__main__':main()
