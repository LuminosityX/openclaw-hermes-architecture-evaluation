# OpenClaw Task Framework Evaluation

`main` focuses on **OpenClaw only**, organized around six dimensions of using an agent framework to complete tasks. Hermes and the former eleven-dimension comparison are historical references, outside the current test scope.

The current work is the [full experiment campaign](evaluation/full-campaign.md): finish the frozen 60-family, 257-scenario scope, audit its completion, then write one unified source-backed architecture analysis. Calibrated families execute their formal repetitions in batches while remaining adapters are implemented. Earlier pilots and the [exploratory source review](evaluation/evidence/source-followup-20261026/README.md) remain historical exploratory evidence; they do not complete this campaign.

The current campaign targets **OpenClaw 2026.10.7**, release commit `157d8c2bc3ea2fa183afdc11088e69690bf8e64e`, checked against GitHub stable and npm `latest` on 2026-10-26. The exact [campaign pin](evaluation/design/evaluation-matrix.json) is fixed for reproducibility. See the [current-version execution guide](evaluation/current-version.md); newer dependency installations run on disposable GitHub-hosted machines, not this local workspace.

[Current-release evidence](evaluation/evidence/current-stable-20261026/README.md) now contains valid two-block pilots for all three first-wave studies on this version. The earlier local build remains harness-bootstrap evidence only.

**Status:** [144 of 257 scenarios have completed formal cloud execution](evaluation/campaigns/full-20261026-batched/README.md), with 585 independent observations: 137 scenarios pass and 7 retain failed acceptance observations. Another 113 scenarios remain incomplete. Running batches and missing adapters are not counted. Unified architecture analysis remains locked until the complete execution audit passes.

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

The [architecture tradeoff studies](evaluation/architecture-studies.md) provide hypotheses for the eventual unified analysis. During the full campaign, source reading supports adapter implementation and harness repair; new architecture interpretations wait until the completion audit passes.

The [historical bootstrap record](evaluation/evidence/README.md) contains native exploratory observations on an existing `2026.9.2` installation. It validates the test chain and is excluded from current-release conclusions. Runtime state was ephemeral and bounded; only a small synthetic JSON evidence record is retained.

Measure actual task outcomes and independently observed effects. Keep failed, cancelled and incomplete attempts in denominators; missing counters or prices remain unknown. A passing CI check validates repository tooling, not OpenClaw reliability, safety or task quality.

## Historical materials

`archive/v6` is the locked historical branch at `a33644efc9490ff771d058ebf047f08550e4ccb3`. `v6/` on `main` remains unchanged and retains the former OpenClaw/Hermes controllers, fixtures, frozen protocol, source references, dependency snapshots and Windows bundle. Do not use those paired controllers as the current OpenClaw runner.

Historical product pins and grades apply only to the [V6 protocol](v6/protocol/protocol_v1.json). See the [historical methodology](docs/history/v6-methodology.md), [historical reproduction guide](docs/history/v6-reproduction.md), [evidence review](docs/history/v6-evidence-review.md) and [provenance](docs/provenance.md). Each future OpenClaw run must independently pin its installed revision, configuration, plugins, model and provider; historical pins are not new-run defaults.

Raw trajectories, state databases, runtime installations, results and credentials stay outside version control. Repository documentation is in English; frozen inputs, upstream quotations and multilingual test strings retain their original language.

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for contribution, reporting and licensing terms.
