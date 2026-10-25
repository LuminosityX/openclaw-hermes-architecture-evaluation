# Agent 架构评估代码归档

归档 OpenClaw/Hermes V6、早期基准、四家 Agent 评估的实验代码、公开夹具、评分方案、操作脚本和已引用源码。原始日志及结果保存在原机器的 V6 本地记录归档中。

## 目录

- `experiments/openclaw-hermes-v6/`：V6 执行、故障、协议、观测、安装恢复等脚本与夹具。
- `experiments/` 其他目录：早期试跑和基准代码。
- `agent-eval/`：四家 Agent 协调代码、任务定义与原交接说明。
- `design/`：固定实验协议、评分与设计材料。
- `dependencies/`：上游版本、锁文件。
- `references/`：原实验引用的源码原文件、SHA256 与许可证。
- `SOURCE_MANIFEST.json`：原文件位置、归档位置及校验值。

## 恢复说明

这是保留历史代码的归档，不含安装后的依赖和完整上游代码库。脚本中的历史绝对路径保持原样，以便与原始记录对应；重跑前应按 `HISTORICAL_LAYOUT.json` 准备路径或调整配置。V6 的 runtime.py 依赖原四家 Agent 工作目录中的 pilot_coordinator.py，后者进一步依赖交接目录 tools/prepare_run.py；这些代码均已一并归档。

依赖应按锁定版本重新安装，普通用例共享只读基线，仅安装、升级与破坏性测试建立独立可写环境。真实服务凭据由运行环境提供，不能从本仓库取得。历史运行入口包含真实模型调用，复现前应先配置预算和模型通道。

原始数据、运行日志、数据库、服务凭据、安装缓存和完整运行环境不作为代码上传。private-fixtures 保存人工编写的评分代码和合成测试数据，不包含实际服务凭据。

## 引用与许可

references/pinned-source-files 中的上游源码仅用于核验原实验结论，保留原作者权利，许可证见 references/licenses。包格式测试仅覆盖共同的 Skill/MCP 内容，不代表任意外来插件可原样执行。
