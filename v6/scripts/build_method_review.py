"""Publish the unchanged frozen rubric alongside the evidence table."""
import html,json,hashlib
from runtime import R
from pathlib import Path
D=Path('/root/output/oc-hermes-formal-design-20261024');p=json.loads((D/'protocol_v1.json').read_text());esc=html.escape
style='body{font:16px/1.7 system-ui,sans-serif;max-width:1250px;margin:35px auto;padding:0 24px;color:#17212d}table{border-collapse:collapse;width:100%}td,th{border:1px solid #cdd5de;padding:12px;vertical-align:top}th{background:#edf2f7}li{margin-bottom:8px}.note{background:#f2f6fa;padding:15px}code{overflow-wrap:anywhere}'
b=['<!doctype html><meta charset="utf-8"><title>11维评分标准与审核边界</title><style>'+style+'</style><h1>11维评分标准与审核边界</h1>']
b+=['<p class="note">本轮实验仅比较固定版本 OpenClaw 与 Hermes；不代表五产品归一化，不包含未执行的 Windows/macOS 或移动端体验。评分器只计算冻结指标；架构解释由执行者核对源码和原始记录，同事审核尚未签认。后续用户已取消实验总预算限制，冻结协议中的旧预算文本不再作为执行门禁。</p>']
b+=['<h2>先判断实验能否用于比较</h2><p>两者使用同一 DeepSeek Flash，主任务 high，真实调用与固定协议夹具分开。权限、有效工具能力、任务输入和验收对齐；实际模型费用包含辅助调用、训练、失败与重试。先以独立真值验收交付，再比较速度与成本；模型自己声称完成不算通过。</p><p>配置、隔离环境、记录器或解析器错误单列为无效尝试，保留原记录并修复；不能计作产品弱。未拥有执行器的平台标为不可用，不得推定通过或失败。</p>']
b+=['<h2>如何判子项领先</h2><ul><li>功能：每个冻结用例至少3个独立新实例/会话，结果须重复一致；按用例类别等权的通过率差达到20个百分点才记方向，否则按已验证的相当或权衡处理；结果不稳定则保留不确定。</li><li>定量：至少6个独立配对簇；同一服务实例中的多批请求、同一profile中的3轮任务不冒充独立样本。使用2000次分簇配对自助法和95%区间。主统计是配对几何均值比；实际累计花费另报，二者不是同一统计量。</li><li>速度、内存、CPU及扩展效率：点估计达到1.20倍的预设实质差距，且区间排除相等才记领先；API费用门槛为1.10倍。区间完全落在等效区间内才记相当，宽区间不默认相当。</li><li>实现和操作路线：依据实际公共接口与runbook审核，不以代码行数或单一开发者编写速度排名；操作逻辑步骤不能因合并成一条脚本而减少。</li></ul>']
b+=['<h2>如何得到强／中／弱</h2><p>子项OC领先记+1，Hermes领先记−1，已验证相当记0；按下表权重计算净优势区间I。未确定的子项保留其正负权重范围，不记0。关键门槛有证据、且可判别权重达到80%后：I整体≥25则OC强/Hermes弱；整体≤−25则OC弱/Hermes强；整体在(−25,25)内则两者中；其余未定档。有效实验中已证实的产品关键失败可覆盖净优势，双边关键失败可双弱。</p><p>“弱”仅表示在本轮同条件需求上存在已测相对劣势，不表示产品不能正常使用。“中”可能来自同样通过，也可能来自不同长处互相抵消。缺少平台、数据或关键门槛证据时，不能为了凑齐11格而填中。</p>']
b+=['<h2>11维、33子项与权重</h2><table><thead><tr><th>维度</th><th>子项及权重</th><th>实际测什么</th><th>关键门槛</th></tr></thead><tbody>']
for d in p['dimensions']:
 b.append('<tr><td>'+esc(d['id']+' '+d['name'])+'</td><td>'+''.join('<p>'+esc(c['id']+' '+c['label'])+'：'+str(c['weight'])+'%</p>' for c in d['criteria'])+'</td><td>'+''.join('<p>'+esc(c['measurement_definition'])+'</p>' for c in d['criteria'])+'</td><td>'+('<br>'.join(esc(x) for x in d['critical_gates']) or '无单独关键失败项；仍需满足有效性及质量资格')+'</td></tr>')
b+=['</tbody></table><h2>费用／资源的预设敏感性</h2><table><tr><th>口径</th><th>API费用</th><th>内存</th><th>CPU</th></tr><tr><td>默认主结果</td><td>40%</td><td>40%</td><td>20%</td></tr><tr><td>API费用优先</td><td>70%</td><td>20%</td><td>10%</td></tr><tr><td>内存优先</td><td>20%</td><td>70%</td><td>10%</td></tr></table><p>这些口径均在正式评分前冻结。若随权重翻转，应报告条件，不宣布无条件冠军；首次任务和学习场景各自保留有效交付与完整账本，不能只挑复用最省的一轮。</p>']
b+=['<h2>审核材料</h2><p><a href="eleven-dimensions-review.html">11维证据表</a> · <a href="observations.json">指标观测</a> · <a href="partial-grades.json">评分器输出</a> · <a href="../../oc-hermes-formal-design-20261024/protocol_v1.json">冻结完整协议</a> · <a href="../../oc-hermes-formal-design-20261024/score_protocol.py">评分器源码</a> · <a href="../evidence/source-architecture-index.json">固定版本架构依据</a></p>']
b+=['<p>评分器SHA-256：<code>'+esc(p['scorer_sha256'])+'</code>。任何缺口或判据修订必须另行标明，不能静默改动冻结协议后重写先前结果。</p>']
(R/'results/scorecard-method.html').write_text(''.join(b));print('FROZEN_METHOD_REVIEW_WRITTEN',len(p['dimensions']))
