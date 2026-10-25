"""Evidence-reviewed public implementation routes and actual native lifecycle.
Route review is by this source/evidence assessment; colleague signoff stays pending.
"""
import json
from runtime import R,save

def main():
 paths=[R/'results/extensions.json',R/'results/executor-routes.json']
 if not all(p.exists() for p in paths):return
 extensions,executors=[json.loads(p.read_text()) for p in paths]
 if len(extensions)!=6 or len(executors)!=6:return
 observations=json.loads((R/'results/observations.json').read_text());functional=[];routes=[];lifecycle=[]
 for unit in range(1,4):
  for case,key in [('X01','tool_contract'),('X02','hook_contract'),('X03','context_contract'),('X04','passed')]:
   values={}
   for family in ['openclaw','hermes']:
    row=next(r for r in (executors if case=='X04' else extensions) if r['unit']==unit and r['family']==family);value=row[key]
    if case=='X04':
     calls=json.loads((R/'runs-executor'/f'u{unit}'/family/'controlled-requests.json').read_text());value=value and row['persisted_user_history'] and row['ordinary_route_preserved'] and row['provider_requests']==0 and any(c['main'] for c in calls)
    values[family]=bool(value)
   functional.append(dict(unit=f'{case}-u{unit}',case=case,oc=values['openclaw'],hermes=values['hermes']))
   routes.append(dict(unit=f'{case}-u{unit}',case=case,oc=0,hermes=0,reviewed=True,evidence=['results/extensions.json','results/executor-routes.json','scripts/run_extensions.py','scripts/run_executor.py'],review_note='Both use documented public SDK/plugin interfaces; no core branch. Hermes supplies an ACP service for its public external-process provider. Source/evidence route assessment by Codex; colleague signoff pending.'))
  for case in ['register','update','disable','uninstall']:
   values={}
   for family in ['openclaw','hermes']:
    row=next(r for r in extensions if r['unit']==unit and r['family']==family);value=all(row[k] for k in ['tool_contract','hook_contract','context_contract']) if case=='register' else row[case+'_contract'];values[family]=bool(value)
   lifecycle.append(dict(unit=f'{case}-u{unit}',case=case,oc=values['openclaw'],hermes=values['hermes']))
 evidence=['results/extensions.json','results/executor-routes.json','evidence/extensions-context-contract-adjudication.json','evidence/executor-authorized-local-scope.json']
 observations['metrics']['D07a']=dict(pairs=functional,evidence=evidence,scope='Matched Unicode tool, pre-call veto, actual old-assistant context filtering with prior user retained, finite local executor and ordinary-route control. Local executor integration is not an equal-sandbox claim.')
 observations['metrics']['D07b']=dict(pairs=routes,evidence=evidence,scope='Public SDK/plugin route class zero for both; protocol implementation and required durable context contract are described separately, not graded by lines of code.')
 observations['metrics']['D07c']=dict(pairs=lifecycle,evidence=evidence)
 complete=all(r['tool_contract'] and r['hook_contract'] and r['context_contract'] for r in extensions) and all(r['passed'] for r in executors)
 observations.setdefault('validity',{})['D07']={key:dict(status='pass' if complete else 'fail',evidence=evidence) for key in ['扩展必须实际加载和调用，不能只看配置或loaded标签','不得修改框架源码补出能力后把改进成绩算作原产品']}
 observations.setdefault('gates',{})['D07']={'在文档要求的刷新/重启后，已禁用或卸载的扩展不得继续改变新任务':dict(oc='pass' if all(r['disable_contract'] and r['uninstall_contract'] for r in extensions if r['family']=='openclaw') else 'fail',hermes='pass' if all(r['disable_contract'] and r['uninstall_contract'] for r in extensions if r['family']=='hermes') else 'fail',evidence=['results/extensions.json'])}
 save(R/'results/observations.json',observations)
 from assemble_observations import main as refresh
 refresh()
if __name__=='__main__':main()
