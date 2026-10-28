# Agent Platform and Harness Architecture Evaluation

Architecture research for **Codex, DeepSeek Harness (DSH), and OpenClaw**, across two complementary layers: how a system hosts agent work, and how its harness manages each execution. Six dimensions—reliability, security, performance, cost, extensibility, and observability—apply to both layers.

## Live CI

[![Comparison CI](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/workflows/comparison-calibration.yml/badge.svg?branch=research%2Fcomparison-calibration)](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/workflows/comparison-calibration.yml?query=branch%3Aresearch%2Fcomparison-calibration)

[View live comparison runs, individual jobs, logs, and artifacts](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/workflows/comparison-calibration.yml?query=branch%3Aresearch%2Fcomparison-calibration). GitHub supplies the badge and run page; the badge reflects the latest workflow outcome, while the run page shows jobs currently in progress. The table below tracks research work, updated from the repository ledger; it does not automatically reflect a running job.

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

**最近一次会话校准：** success（三个独立 runner 的汇总）。[查看运行和各单元](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40622793927)。

**既有 OpenClaw 冻结实验：** 253/257 场景已测，224 通过、29 保留失败观察，4 已确认不适用；969 个独立观察。[审计与证据](evaluation/campaigns/full-20261026-batched/README.md)。

看板由 [进度台账](comparison/progress.json) 和冻结审计生成，反映仓库最新提交，运行中状态需更新台账。详见 [维护说明](comparison/README.md)。
<!-- comparison-dashboard:end -->

## Research and evidence

| Start here | Contents |
| --- | --- |
| [Three-product workspace](comparison/README.md) | Scope, dashboard maintenance and evidence rules |
| [First-wave protocols](comparison/first-wave-protocol.md) | Concrete platform and harness scenarios, controls and limits |
| [Execution plan](comparison/plan.md) | Priorities, comparison tracks and evidence reuse |
| [OpenClaw campaign](evaluation/README.md) | Frozen six-dimension design, tooling and execution guides |
| [OpenClaw architecture report](evaluation/reports/full-20261026-architecture.md) | Source-backed results and tradeoffs for the frozen campaign |
| [Chinese scenario observations](evaluation/reports/full-20261026-observations-zh.md) | Experiment-by-experiment facts and limitations |
| [Historical V6](docs/history/v6-methodology.md) | Earlier OpenClaw/Hermes protocol; not part of the new comparison |

The completed OpenClaw campaign used version 2026.10.7, commit `157d8c2bc3ea2fa183afdc11088e69690bf8e64e`. Its observations are historical evidence for that configuration, not completed three-product experiments. The new DSH target is the preview `0.2.2-alpha.2`; each hosted run records its exact installation and does not run Codex.

## Repository map

- `comparison/` — cross-product protocols, progress ledger and hosted calibration.
- `evaluation/` — frozen OpenClaw design, runner, tests, reports and evidence.
- `v6/` — immutable historical archive; `SOURCE_MANIFEST.json` records its integrity.
- `docs/` — methodology, reproduction, provenance and historical guides.
- `.github/workflows/` — checks and disposable hosted experiment jobs.

## Validate locally

These commands inspect repository data and code; they do not install products or run experiments.

```sh
python3 tools/check_repository.py
python3 evaluation/tools/check_design.py
python3 comparison/dashboard.py --check
python3 -m unittest discover -s evaluation/tests -v
```

The [contribution guide](CONTRIBUTING.md), [security policy](SECURITY.md), [license](LICENSE), and [third-party notices](THIRD_PARTY_NOTICES.md) remain applicable. Synthetic experiment output, version pins and measurement limits are required before drawing product conclusions.
