# 三系统架构测评工作区

本目录是 Codex、DeepSeek Harness（DSH）和 OpenClaw 新一轮测评的入口。[执行方案](plan.md)和[首批具体协议](first-wave-protocol.md)定义两层研究问题、首批实验和验收；[进度台账](progress.json)记录各产品每项工作的状态。既有 [OpenClaw 冻结实验](../evaluation/README.md)和 [V6 历史资料](../v6/)保持原路径与证据边界，不代表已完成三方比较。

## 维护进度

修改 `progress.json` 中对应单元的状态、证据路径和备注，运行 `python3 comparison/dashboard.py` 更新根目录 README；提交台账、证据和 README。`python3 comparison/dashboard.py --check` 检查生成内容是否同步。GitHub Actions 页面显示运行中的步骤；会话校准结束后，汇总 job 会将最新运行链接及结果写入研究分支台账并生成 README。其他实验状态由负责人更新并提交；台账不自动推断正式测评完成。每个单元代表一项工作，不代表一个实验样本，也不能将百分比解释为实验成功率。

状态：`planned` 待开始、`in_progress` 进行中、`blocked` 阻塞、`done` 已完成、`not_applicable` 已确认不适用。`done` 和 `not_applicable` 必须提供仓库内的证据文件；历史证据若协议不同不能直接标记新实验完成。失败但有效且完成验收的实验可以标为 `done`，应在证据中保留失败结果。
