OpenClaw / Hermes 11维完整实验设计 v1（审核稿）

先打开 OC_Hermes_完整实验协议_v1.html 或同名.xlsx。Excel包含16个页签，可在“11维与判据”逐项填写审核意见。
本包是完整的实验设计、判据与评分器，不代表所有新增正式夹具已实现。implementation_readiness.json逐模块列出实施状态。
主线：4类任务×3变体×2次独立重复×2产品=48次真实模型任务；另16次模型诱导走查及36次跨会话训练/复用，共100次真实模型任务运行。其余原生机制使用本地固定协议响应，和真实模型效果分开。
正式主线固定OC v2026.10.6、Hermes v0.22.5；已查官方release和Git tag完整SHA，见version_lock.json。现有Hermes主干试跑不混入稳定版正式样本。

试跑已完成：两家各6/6通过，新模型费用估算共2.15867940元；此后修复与机制测试无真实模型调用。修复和有效差异见“试跑修复与观察.txt”及pilot_evidence。

评分：每维子项与权重预定，净优势与区间决定强/中/弱；相当、权衡和未分胜负有不同状态。实验无效、质量不可比与产品关键失败严格分开。当前只做两家相对分档，不冒充五家归一化。

本地自检（仅Python标准库，无模型调用）：
  python3 validate_protocol.py
  python3 score_protocol.py --selftest
观测数据按observations_template.json填写；先实现所有夹具与E00正反例预检，再把协议改为冻结执行版并重新保存hash。
  python3 score_protocol.py --observations measurements.json --output grades.json
预设敏感性分析（不替代主结果）：
  python3 score_protocol.py --observations measurements.json --profile api_cost_priority --output grades_api.json
  python3 score_protocol.py --observations measurements.json --profile memory_priority --output grades_memory.json
评分器和协议内容均有hash校验，不接受旧判据或不同同伴集合的结果。重新生成审核文档可运行build_protocol.py，正式冻结以后应新建版本，不覆盖原数据。

NEXT_THREAD_PROMPT.txt为接续实施说明。已有模型试跑无需再跑；新正式付费批次尚未启动。原50元总上限、旧未知调用预留、无新付费云资源等限制保留。
本包不含真实API密钥、日常账号状态或框架runtime目录。vendor目录是公开pluggy1.5.0源码与wheel，用于真实项目题目种子，保留来源和SHA。

本轮还识别了审批合同混杂，原12例不用于公平性能/费用分档。两家同权原生正控现均4/4通过；完整正式采用共同安全/授权合同和所有代码执行路径清单。Excel审核意见采纳后需更新JSON协议版本及哈希，不能只改表面数字。

E13学习指应用层资产复用，不是模型权重训练；独立复现历史项目种子：python3 reproduce_seed.py。当前模型主线仍是12次试跑，新正式设计100次任务运行尚未执行。
