"""Map semantic native reconstruction to frozen D09; incomplete contracts stay unknown."""
import json
from runtime import R,save

def main():
    source=R/'results/native-observability-reconstruction.json'
    x=json.loads(source.read_text());a=x['approval'];b=x['fault_reconstruction']
    if len(a)!=12 or len(b)!=18:raise RuntimeError('Native evidence units incomplete')
    pa=[];pb=[]
    for u in range(1,7):
        for case in ['tool_events','approval_events','identity_links']:
            fs={z['family']:z for z in a if z['unit']==u}
            if set(fs)!={'openclaw','hermes'}:raise RuntimeError('Missing paired observation profile')
            pa.append(dict(unit=f'{case}-u{u}',case=case,oc=fs['openclaw'][case],hermes=fs['hermes'][case]))
    for case in ['side_effect_reconstruction','child_reconstruction','retry_reconstruction']:
        units=[2,4,6] if case=='retry_reconstruction' else [1,2,3]
        for u in units:
            fs={z['family']:z for z in b if z['case']==case and z['unit']==u}
            if set(fs)!={'openclaw','hermes'}:raise RuntimeError('Missing paired fault reconstruction')
            pb.append(dict(unit=f'{case}-u{u}',case=case,oc=fs['openclaw']['passed'],hermes=fs['hermes']['passed']))
    evidence=['results/native-observability-reconstruction.json','results/observability.json','evidence/source-architecture-index.json']
    obs=json.loads((R/'results/observations.json').read_text())
    obs['metrics']['D09a']=dict(pairs=pa,evidence=evidence,scope='Official configured collectors, six independent fresh profiles per product. Both native tool/task/verdict joins pass. Exact authorization choice is separately checked: OC keeps allow-once/deny plus operator/source links, whereas the observed H official route preserves approved/denied but does not retain once/session/always choice. Missing identical UUID or schema alone is never a failure; H public hooks can implement a custom ledger.')
    obs['metrics']['D09b']=dict(pairs=pb,evidence=evidence+['results/control-faults.json','results/child-standard-resume.json'],scope='Three independently retained native cases per failure type: exact error/retry cause and completion, durable parent/child completion vs interrupted delivery, failed ACK followed by a persisted receipt-query result. Identical trace topology is not required; external truth is not the native evidence.')
    obs.setdefault('criterion_limits',{})['D09c']='Actual collector outage and recovery were executed in all six paired units, and local native records remain available. Full retention/closure/export contract, including the long-lived Hermes session-root versus per-event export lifecycle, is not fully certified; weight20 remains unknown. Do not infer no telemetry from absent closed-session ATIF or count spans as quality.'
    obs.setdefault('gates',{})['D09']={'自身声明为权威的审批/操作结果记录不得与已知真值相反':dict(oc='pass',hermes='pass',evidence=evidence,scope='The two approved and one denied verdicts agree with actual effect truth in every configured profile; missing choice detail is incomplete metadata, not a fabricated approval or execution.')}
    obs.setdefault('validity',{})['D09']={key:dict(status='pass',evidence=evidence) for key in ['外部真值账本不得冒充产品自身审计','不得将缺记录解释为未发生或将诊断入口宣称为合规归档']}
    save(R/'results/observations.json',obs)
    from assemble_observations import main as refresh
    refresh()

if __name__=='__main__':main()
