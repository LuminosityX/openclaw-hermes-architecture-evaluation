"""Fixed finite compatibility matrix, keeping declared subsets and tradeoffs visible."""
import json
from runtime import R,save

def load(n):return json.loads((R/'results'/(n+'.json')).read_text())
def main():
 names=['protocols','mcp-contracts','mcp-projection-audit','mcp-original-storage-audit','bundles','setup-imports','context-contract','real-reasoning-contract-audit']
 if not all((R/'results'/(n+'.json')).exists() for n in names):print('D11_WAITING_REQUIRED_CONTRACTS');return
 protocol,mcp,projection,storage,bundles,imports,context,thinking=[load(n) for n in names];native=load('native-suite');faults=load('control-faults');cancel=load('cancellation');legacy=load('legacy-policy-semantics');upgrades=load('upgrades');pairs_a=[];pairs_b=[];pairs_c=[]
 if not(len(protocol)==18 and len(mcp)==len(projection)==12 and len(bundles)==24 and len(imports)==len(context)==len(thinking)==6):raise RuntimeError('Compatibility independent units incomplete')
 for row in bundles:
  if not row['supported_as_declared']:
   control=row.get('conversion_control',{})
   if row['status']!='unsupported_with_source_confirmation' or not all(control.get(k) for k in ['unicode_tool_advertised','unicode_preserved','recipient_called','skill_registered']):raise RuntimeError('Unsupported source format lacks positive same-payload standard-format control')
 for unit in range(1,4):
  for case in ['K01','K02']:
   values={}
   for family in ['openclaw','hermes']:
    wire=[x for x in protocol if x['unit']==unit and x['family']==family];value=len(wire)==3 and all(x['passed'] and x['wire_route_verified'] and x['tool_effect_correct'] for x in wire)
    if case=='K02':
     ctx=next(x for x in context if x['unit']==unit and x['family']==family);thought=next(x for x in thinking if x['unit']==unit and x['family']==family);truncated=next(x for x in faults if x['unit']==unit and x['family']==family and x['kind']=='R03-truncated-stream');c=next(x for x in cancel if x['unit']==unit and x['family']==family);batch=next(x for x in native if x['independent_unit']==unit and x['family']==family and x['kind']=='mcp');value=value and ctx['passed'] and thought['nonempty_reasoning_received'] and thought['task_passed_independent_acceptance'] and truncated['recovered'] and not truncated['partial_accepted_as_success'] and c['nonpersistent_processes_stopped'] and not c['late_effects'] and batch['passed']
    values[family]=bool(value)
   pairs_a.append(dict(unit=f'{case}-u{unit}',case=case,oc=values['openclaw'],hermes=values['hermes']))
  for case in ['K03','K04','K05']:
   values={}
   for family in ['openclaw','hermes']:
    rows=[x for x in mcp if x['unit']==unit and x['family']==family];pro=[x for x in projection if x['unit']==unit and x['family']==family]
    if case=='K03':value=len(rows)==2 and all(x['native_tools_loaded'] for x in rows)
    elif case=='K04':
     basic=len(rows)==2 and all(x['unicode_preserved'] and x['declared_error_visible'] and x['schema_error_visible'] for x in rows) and all(x['structured_semantics_preserved'] for x in pro)
     # Fixed ordinary tool-result path: explicit truncation is honest but
     # does not provide a complete recoverable payload to this consumer.
     # Never generalize this to alternate first-party code-mode routes.
     recoverable=all(x['complete_inline'] or any(p['exact_original'] for p in x['native_spill_files']) for x in pro)
     if family=='openclaw' and not recoverable:
      canonical=[x for x in storage['rows'] if x['unit']==unit]
      recoverable=all(any(e['full_large_content_exact'] for e in x['large_native_events']) for x in canonical)
     value=basic and recoverable
    else:
     entries=[x for x in bundles if x['unit']==unit and x['family']==family];value=len(entries)==4 and all(x['status']=='accepted' and x['primary']['recipient_called'] and x['primary']['unicode_preserved'] and x['primary']['skill_registered'] for x in entries)
    values[family]=bool(value)
   pairs_b.append(dict(unit=f'{case}-u{unit}',case=case,oc=values['openclaw'],hermes=values['hermes']))
  for case in ['K06','O05']:
   values={}
   for family in ['openclaw','hermes']:
    if case=='K06':
     imported=next(x for x in imports if x['unit']==unit and x['family']==family);old=next(x for x in legacy if x['unit']==unit);migrated=old['openclaw']['after_documented_doctor_migration']['passed'] if family=='openclaw' else old['hermes']['current_native_actual']['passed'];value=imported['passed'] and migrated
    else:
     row=next(x for x in upgrades if x['unit']==unit and x['family']==family);phase=[p for p in row['phases'] if p['phase']=='upgraded'];value=len(phase)==1 and phase[0]['passed']
    values[family]=bool(value)
   pairs_c.append(dict(unit=f'{case}-u{unit}',case=case,oc=values['openclaw'],hermes=values['hermes']))
 evidence=['results/'+n+'.json' for n in names]+['results/native-suite.json','results/control-faults.json','results/cancellation.json','results/legacy-policy-semantics.json','results/upgrades.json','evidence/source-architecture-index.json']
 obs=load('observations');obs['metrics']['D11a']=dict(pairs=pairs_a,evidence=evidence,scope='Three wire adapters: basic tools/Unicode/stream completion; common real Flash high reasoning and current Chat batch/stream/error/cancel/context-error contracts. Does not certify every vendor-specific opaque thinking/signature feature or true token capacity.')
 obs['metrics']['D11b']=dict(pairs=pairs_b,evidence=evidence,scope='Two MCP transports, fixed text/schema/error/structured-content and complete640KB recovery on ordinary tool-result route; four package formats use only their common skill/MCP subset. OC native format breadth and H native full spill recovery are opposite observed advantages. No arbitrary plugins/commands/hooks full compatibility or alternate code-mode test is claimed.')
 obs['metrics']['D11c']=dict(pairs=pairs_c,evidence=evidence,scope='Supported cross-agent setup MCP/skills/model fields and declared legacy-policy migration; actual pinned prior/current state/plugin release compatibility. Foreign OAuth/live execution receipts and all foreign conversation formats are outside this supported subset.')
 obs.setdefault('validity',{})['D11']={key:dict(status='pass',evidence=evidence) for key in ['协议HTTP成功不能替代参数/结果语义正确','公开支持子集必须如实标明']}
 obs.setdefault('criterion_limits',{})['D11']='Finite current protocol/content/package/setup list only. Legacy MCP SSE, MCP-specific expired-session/cancel edge cases, and vendor opaque reasoning signatures were not separately exercised; do not call this universal protocol certification.'
 save(R/'results/observations.json',obs)
 from assemble_observations import main as refresh
 refresh()
if __name__=='__main__':main()
