OpenClaw / Hermes 11维比较补测 V5，2026-10-24
当前用户明确要求实测这两家，替代此前方法审查的暂停状态。没有授权运行DSH/Claude/Codex、新付费云资源或手机登录。
真实模型：deepseek-flash，主任务high thinking，禁止模型切换，所有请求与用量经原有审计中继记录。
已安装版本：OpenClaw2026.10.6(fe06181)；Hermes源码5894e750c3dba980d43b25aa29e3958149ba2c61，PM环境Python3.14.9。
两个任务类型，每个三个独立输入变体，每家六次；交替顺序，总计12个首次尝试；每次600秒上限，持续检测完成。
原预算总上限50元保留；新批次保守费用敞口增加不超过15元，保留旧未结清请求的10.2元保守预留。
fixtures是公开输入；private是隐藏验收，仅结束后挂载到评估进程，被测Agent执行期间不能读取。
编码验收26项、数据验收9项；验收器均通过正确与错误实现的正反例检验。
runs保存模型请求响应、启动命令、stderr、产物hash、验收及资源记录，state含PM环境不得打包。
results/pairs.json为已完成真实任务结果。evidence/active.json为当前进程；evidence/live-budget.json为持续费用门禁。
scripts/run_mechanisms.py在真实模型计时批次结束后运行，使用本地固定协议响应、不调用付费模型；真实产品执行真实工具，不能把这类结果当作模型任务质量。
历史两套实验在/root/output/openclaw-hermes-benchmark-20261022和/root/output/openclaw-hermes-nonfunctional-20261022；版本与配置不同，作为补充而不混合统计。
协调者启动时发生过Unix socket路径过长问题，未启动产品或调用模型，记录在evidence/setup-failure-unix-path；不能计为OpenClaw失败。
