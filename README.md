# OpenClaw / Hermes V6 架构评估代码

本仓库当前内容仅保留 V6 的实验代码、测试夹具、评分协议、版本锁定信息及引用源码。早期版本、独立的四家 Agent 评估材料和重复的控制脚本快照已移除。

## 目录

- `v6/scripts/`：V6 实验、分析及审计脚本。
- `v6/fixtures/`、`v6/private-fixtures/`：任务输入、合成数据和验收代码。
- `v6/windows-native-bundle/`：V6 Windows 侧执行材料。
- `v6/protocol/`：V6 使用的冻结协议、评分与校验代码。
- `v6/support/`：V6 直接引用的公共协调、隔离、数据生成和原生工具测试脚本，仅保留所需文件。
- `v6/dependencies/`：版本与依赖锁文件。
- `v6/references/`、`v6/patches/`：V6 引用的上游源码、许可证及对照实验补丁。

## 使用说明

这是 V6 源码归档，未包含安装后的运行环境。原脚本中的历史路径保持原样，重跑前按 `HISTORICAL_LAYOUT.json` 准备路径或调整配置，并安装锁定版本的应用、依赖及工具。`support/` 中的公共脚本属于 V6 的依赖，不包含旧版评估流程和运行结果。

V6 的 102 份原始结果文件及压缩后的日志、数据库和任务记录保留在原机器 `/root/output/oc-hermes-execution-20261024-v6`，未上传本仓库；真实服务凭据也未上传。实验入口可能调用真实模型，重跑前须配置模型通道和预算。

`SOURCE_MANIFEST.json` 记录所保留源码的原始位置、归档位置和校验值，`references/` 中的上游代码按各自许可证使用。
