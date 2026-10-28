# Agent Platform and Harness Architecture Evaluation

本仓库正在扩展为 **Codex、DeepSeek Harness（DSH）和 OpenClaw** 的平台层与 Harness 层架构测评。[三方工作区与方案](comparison/README.md)记录新范围；下方原有实验、报告和运行工具仍属于已冻结的 OpenClaw 专项，不代表三方测评已完成。

<!-- comparison-dashboard:start -->
## 测评进度看板

**三方新协议：** 下表为工作项状态，非实验成功率；历史 OpenClaw 结果不自动计入新协议。

| 层次 / 工作项 | Codex | DSH | OpenClaw |
| --- | --- | --- | --- |
| 平台 · P01 故障域 | 待开始 | 待开始 | 待开始 |
| 平台 · P02 状态与部署 | 待开始 | 待开始 | 待开始 |
| 平台 · P03 资源与并发 | 待开始 | 待开始 | 待开始 |
| 平台 · P04 接入与运维 | 待开始 | 待开始 | 待开始 |
| Harness · H03 压缩与约束 | 待开始 | 待开始 | 待开始 |
| Harness · H04 大工具输出 | 待开始 | 待开始 | 待开始 |
| Harness · H05 恢复与副作用 | 待开始 | 进行中 | 进行中 |
| Harness · H08 工具调度 | 待开始 | 待开始 | 待开始 |
| Harness · H11 审批绑定 | 待开始 | 待开始 | 待开始 |
| Harness · H17 轨迹重建 | 待开始 | 待开始 | 待开始 |

**既有 OpenClaw 冻结实验：** 253/257 场景已测，224 通过、29 保留失败观察，4 已确认不适用；969 个独立观察。[审计与证据](evaluation/campaigns/full-20261026-batched/README.md)。

看板由 [进度台账](comparison/progress.json) 和冻结审计生成，反映仓库最新提交，运行中状态需更新台账。详见 [维护说明](comparison/README.md)。
<!-- comparison-dashboard:end -->

## Existing OpenClaw campaign

The existing frozen campaign focuses on **OpenClaw only**, organized around six dimensions of using an agent framework to complete tasks. Hermes and the former eleven-dimension comparison are historical references, outside the current test scope.

The [full OpenClaw campaign](evaluation/full-campaign.md) completed its frozen 60-family, 257-scenario scope and completion audit. Earlier pilots and the [exploratory source review](evaluation/evidence/source-followup-20261026/README.md) remain separate historical evidence.

The frozen campaign targeted **OpenClaw 2026.10.7**, release commit `157d8c2bc3ea2fa183afdc11088e69690bf8e64e`, checked against GitHub stable and npm `latest` on 2026-10-26. The exact [campaign pin](evaluation/design/evaluation-matrix.json) is fixed for reproducibility. See the [current-version execution guide](evaluation/current-version.md); newer dependency installations run on disposable GitHub-hosted machines, not this local workspace.

[Current-release evidence](evaluation/evidence/current-stable-20261026/README.md) now contains valid two-block pilots for all three first-wave studies on this version. The earlier local build remains harness-bootstrap evidence only.

**Status:** [253 of 257 scenarios have completed formal cloud execution](evaluation/campaigns/full-20261026-batched/README.md), with 969 independent observations: 224 scenarios pass and 29 retain failed acceptance observations. 4 other scenarios have verified native nonapplicability, disclosed separately from measured coverage. No scenarios remain incomplete. The complete execution audit has passed. The completed audit now permits unified source-backed architecture analysis.

Read the [completed campaign architecture analysis](evaluation/reports/full-20261026-architecture.md) for source-backed mechanisms, cross-dimension tradeoffs, measurement limits and the retained failed acceptance observations.

The [Chinese experiment-by-experiment factual report](evaluation/reports/full-20261026-observations-zh.md) describes all 257 scenario setups and observations. Its [per-unit evidence compilation](evaluation/reports/full-20261026-observations-draft-zh.md) retains measured fields and source links; machine-translated labels in that appendix are marked as unreviewed.


| Dimension | Focus | Planned families |
| --- | --- | --- |
| Reliability / 可靠性 | Task loss, duplicate effects, state consistency, retries, cancellation, recovery and dependency failures | 15 |
| Security / 安全性 | User privacy, isolation, permissions, prompt injection, network egress, gateway access and extension supply chains | 12 |
| Performance / 性能 | Problem-solving success, deliverable quality, latency, concurrency, overload and sustained capacity | 10 |
| Resource usage and cost / 资源占用与成本 | CPU, RSS/PSS/cgroup memory, swap, disk/inodes/IO, network, processes, tokens and USD charges | 7 |
| Extensibility / 可扩展性 | Public plugin interfaces, hooks, lifecycle, composition, tools and integration contracts | 9 |
| Observability / 可观测性 | Accessible agent trajectories, event linkage, export, fault reconstruction and observer overhead | 7 |

## Getting started

Requirements: Git and Python 3.11 or later; no third-party Python packages are needed for these commands.

```sh
git clone https://github.com/zyw02/openclaw-hermes-architecture-evaluation.git
cd openclaw-hermes-architecture-evaluation
python3 tools/check_repository.py
python3 evaluation/tools/check_design.py
python3 -m unittest discover -s evaluation/tests -v
python3 evaluation/tools/suite.py list
```

Select a plan by dimension or case. These commands only print JSON; they never start OpenClaw, install software, or call a provider.

```sh
python3 evaluation/tools/suite.py plan --dimension reliability
python3 evaluation/tools/suite.py plan --dimension security --case SEC-08
python3 evaluation/tools/suite.py plan --dimension performance --phase real-model
python3 evaluation/tools/suite.py plan --phase all
```

The default plan contains deterministic mechanism tests. Actual task capability, model prompt-injection susceptibility and provider charges require real usage. The selected provider is `deepseek-flash`; the user explicitly chose no campaign monetary ceiling. Selecting a plan alone does not enable execution.

## Current evaluation

Start with the [evaluation guide](evaluation/README.md), [experiment catalogue](evaluation/experiment-catalogue.md), [measurement contract](evaluation/measurement-contract.md) and [methodology](docs/methodology.md). The [matrix](evaluation/design/evaluation-matrix.json) defines the current six dimensions and required metrics. The [reproduction guide](docs/reproduction.md) explains validation, selection and execution prerequisites.

The [architecture tradeoff studies](evaluation/architecture-studies.md) provide hypotheses for the eventual unified analysis. The completed campaign includes a source-backed architecture analysis linked above.

The [historical bootstrap record](evaluation/evidence/README.md) contains native exploratory observations on an existing `2026.9.2` installation. It validates the test chain and is excluded from current-release conclusions. Runtime state was ephemeral and bounded; only a small synthetic JSON evidence record is retained.

Measure actual task outcomes and independently observed effects. Keep failed, cancelled and incomplete attempts in denominators; missing counters or prices remain unknown. A passing CI check validates repository tooling, not OpenClaw reliability, safety or task quality.

## Historical materials

`archive/v6` is the locked historical branch at `a33644efc9490ff771d058ebf047f08550e4ccb3`. `v6/` on `main` remains unchanged and retains the former OpenClaw/Hermes controllers, fixtures, frozen protocol, source references, dependency snapshots and Windows bundle. Do not use those paired controllers as the current OpenClaw runner.

Historical product pins and grades apply only to the [V6 protocol](v6/protocol/protocol_v1.json). See the [historical methodology](docs/history/v6-methodology.md), [historical reproduction guide](docs/history/v6-reproduction.md), [evidence review](docs/history/v6-evidence-review.md) and [provenance](docs/provenance.md). Each future OpenClaw run must independently pin its installed revision, configuration, plugins, model and provider; historical pins are not new-run defaults.

Raw trajectories, state databases, runtime installations, results and credentials stay outside version control. Repository documentation is in English; frozen inputs, upstream quotations and multilingual test strings retain their original language.

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for contribution, reporting and licensing terms.
