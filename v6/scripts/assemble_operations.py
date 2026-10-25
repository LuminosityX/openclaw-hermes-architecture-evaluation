"""D10: reviewed manual pinned-release runbooks, not native updater automation."""
import json,time
from runtime import R,save

def load(n):return json.loads((R/'results'/(n+'.json')).read_text())
def main():
 if not all((R/'results'/(n+'.json')).exists() for n in ['install-rebuilds','canonical-backup-layout']):print('D10_WAITING_INSTALL_AND_LAYOUT_CONTROLS');return
 installs=load('install-rebuilds');layout=load('canonical-backup-layout');corrupt=[x for x in load('storage-faults') if x['kind']=='corruption'];upgrades=load('upgrades')
 if not(len(installs)==len(corrupt)==len(upgrades)==6 and len(layout)==3):raise RuntimeError('Independent operation units incomplete')
 if not all(x['passed'] for x in installs+layout+corrupt+upgrades):raise RuntimeError('Review a failed native operation before creating an ordinal judgement')
 actions={
 'O01':{'openclaw':['请求锁定发布的原生应用/依赖安装'],'hermes':['请求锁定源码/锁文件的原生应用依赖安装']},
 'O02':{'openclaw':['原生配置诊断','恢复最后有效配置字节'],'hermes':['原生配置诊断','恢复最后有效配置字节']},
 'O03':{'openclaw':['原生全量备份并校验','原生恢复到暂存目录','离线激活原生状态目录（包含标准位置配置）','离线激活外部工作区'],'hermes':['原生home备份','保存外部工作区伴随副本','原生home导入','恢复外部工作区']},
 'O05':{'openclaw':['选择锁定目标发行物','请求对应原生应用及依赖安装','停止旧运行单元','以原状态启动目标发行物'],'hermes':['选择锁定目标源码发行物','请求对应原生应用及依赖安装','停止旧运行单元','以原状态启动目标发行物']},
 'O06':{'openclaw':['建立经校验的原生恢复点','选择旧发行物','停止更新后运行单元','原生恢复到暂存目录','激活完整原生状态目录','激活外部工作区','从恢复点启动旧发行物'],'hermes':['建立原生home恢复点','保存外部工作区伴随副本','选择旧发行物','停止更新后运行单元','原生home导入','恢复外部工作区','从恢复点启动旧发行物']}}
 evidence=['results/install-rebuilds.json','results/canonical-backup-layout.json','results/storage-faults.json','results/upgrades.json','results/upgrade-current-job-audit.json','evidence/source-architecture-index.json','results/ops-runbook-review.json']
 review=dict(at=time.time(),reviewer='Execution agent: native output, pinned source and full-runbook review; colleague sign-off pending',actions=actions,count_unit='Required logical operator actions in the listed manual workflow; combining commands does not remove an action. Native validation internals, evaluator namespace/mount/transport mirroring, test acceptance, failed fixture commands and archive compression are excluded.',prerequisites='Pinned source/release artifacts and machine tool/byte cache are preprovided on both sides, as in E00. O05 assesses the manual pinned-artifact transition; O06 includes establishing its recovery point. This is not a measurement of download speed, automatic updater orchestration or an in-place live-upgrade GUI.',layout_control='External benchmark OC config originally added a third asset-copy operation. Actual three canonical-layout controls preserve all native semantics using profile+workspace activation only. H external-workspace capture and restoration remain counted.',scope='Conservative manual pinned-release and backup-based workflows only; native latest-channel updater UX, zero-downtime rollout and long-term schema/plugin compatibility remain untested.')
 save(R/'results/ops-runbook-review.json',review);first=[];last=[];burden=[]
 for u in range(1,4):
  rows={f:next(x for x in installs if x['unit']==u and x['family']==f) for f in ['openclaw','hermes']};cs={f:next(x for x in corrupt if x['unit']==u and x['family']==f) for f in rows};us={f:next(x for x in upgrades if x['unit']==u and x['family']==f) for f in rows}
  for case in ['O02','O03','O04']:
   values={f:(rows[f]['native_configuration_fault_diagnosed'] and rows[f]['native_repaired_tool_delivery']['passed']) if case=='O02' else cs[f]['passed'] for f in rows};first.append(dict(unit=f'{case}-u{u}',case=case,oc=bool(values['openclaw']),hermes=bool(values['hermes'])))
  for case in ['O01','O05','O06']:
   values={f:rows[f]['native_initial_tool_delivery']['passed'] if case=='O01' else all(p['passed'] for p in us[f]['phases'] if p['phase']==('upgraded' if case=='O05' else 'rollback-recovered')) for f in rows};last.append(dict(unit=f'{case}-u{u}',case=case,oc=bool(values['openclaw']),hermes=bool(values['hermes'])))
  for case in actions:burden.append(dict(unit=f'{case}-u{u}',case=case,oc=len(actions[case]['openclaw']),hermes=len(actions[case]['hermes']),reviewed=True,evidence=evidence,scope=review['scope']))
 obs=load('observations');obs['metrics']['D10a']=dict(pairs=first,evidence=evidence,scope='Original same-logical-layout corruption restores supply O03/O04 semantic assertions on the same independent source units; they are not counted as separate fault samples. Fresh config diagnosis/repair is a separate case.')
 obs['metrics']['D10b']=dict(pairs=burden,evidence=evidence,scope=review['scope']);obs['metrics']['D10c']=dict(pairs=last,evidence=evidence,scope='Native independent app rebuild plus actual previous/current releases, state/plugin behavior and pre-update-backup rollback; no universal backward-compatibility promise.')
 obs.setdefault('gates',{})['D10']={'官方恢复报告完成后，声明备份范围的关键状态不得无告警不可用':dict(oc='pass',hermes='pass',evidence=evidence)};obs.setdefault('validity',{})['D10']={'协调者错误不能计为产品运维失败':dict(status='pass',evidence=evidence)}
 save(R/'results/observations.json',obs)
 from assemble_observations import main as refresh
 refresh()
if __name__=='__main__':main()
