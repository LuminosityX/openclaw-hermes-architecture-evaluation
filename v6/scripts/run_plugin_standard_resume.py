"""Complete R09's manual-resume observation on the three original OC units.
This does not add fault-injection samples or turn an interrupted service into
uninterrupted survival. Original fatal-fault outcomes remain unchanged.
"""
import json,os,shutil,time
from runtime import R,OLD,save,read_config
from controlled import Plan,shell
from gateway import Gateway

def one(unit):
 run=R/'runs-plugin-standard-resume'/f'u{unit}'/'openclaw'
 if (run/'result.json').exists():return json.loads((run/'result.json').read_text())
 if run.exists():raise RuntimeError('Partial native plugin continuation check retained '+str(run))
 original=R/'runs-gateway-plugin-fault'/f'u{unit}'/'openclaw';prior=json.loads((original/'result.json').read_text())
 if not prior['valid_fault'] or not prior['manual_owner_restart_needed']:raise RuntimeError('The original fatal plugin observation is not eligible')
 run.mkdir(parents=True);shutil.copytree(original/'state',run/'state',symlinks=True,ignore=shutil.ignore_patterns('*.sock'));shutil.copytree(original/'workspace',run/'workspace',symlinks=True);(run/'workspace/SURVIVED').unlink(missing_ok=True);p=run/'state/openclaw.json';cfg=read_config(p);cfg.setdefault('cron',{})['enabled']=False;save(p,cfg);fixture=Plan(run,'openclaw',[shell('python3 /workspace/survivor.py')]);gateway=Gateway(run,'openclaw',fixture);print('PLUGIN_STANDARD_RESUME_START',unit,flush=True)
 try:
  gateway.start();ready=time.monotonic();response=gateway.chat('Continue the original authorized task from its retained state.','fault-target',timeout=40);first=next((c['request'] for c in fixture.calls if c['main']),{});retained='FAULT_TARGET Run the controlled registered plugin fault plan.' in json.dumps(first.get('messages',[]));row=dict(unit=unit,family='openclaw',source_fault_unit=str(original.relative_to(R)),original_service_interrupted=True,original_fault_injections_added=0,standard_continue_submissions=1,seconds_after_native_ready=time.monotonic()-ready,original_task_history_visible=retained,same_original_conversation_continued=retained and response.get('status')==200 and (run/'workspace/SURVIVED').exists(),response=response,scope='One explicit standard continuation on the original fault-target session after normal service availability; snapshot of this same original source unit, not a new statistical unit. No prior-result text injected, no plugin/core patch, and no repeat crash request. Original service/neighbor outage records remain failures of uninterrupted containment.');save(run/'result.json',row);print('PLUGIN_STANDARD_RESUME_DONE',unit,row['same_original_conversation_continued'],flush=True)
  if not retained:raise RuntimeError('No retained original task context; do not credit a new unrelated task as recovery')
  return row
 finally:gateway.stop();fixture.close()

def main():
 os.chdir(OLD);rows=[]
 for unit in range(1,4):rows.append(one(unit));save(R/'results/plugin-standard-resume.json',rows)
 print('PLUGIN_STANDARD_RESUME_COMPLETE',len(rows),flush=True)
if __name__=='__main__':main()
