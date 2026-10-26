# OpenClaw evaluation

This directory evaluates OpenClaw task execution on `main` across exactly six dimensions and a 60-family, 257-scenario coverage plan. Hermes is excluded. The [bounded pilot runner](runner/README.md) implements actual native Gateway pilots for the first three architecture studies. Full case-family coverage and real-model workloads remain planned; a pilot result is not full-family completion.

## Entry points

1. [Experiment matrix](design/evaluation-matrix.json): authoritative product scope, six dimensions, metric units, coverage tags and cases.
2. [Experiment catalogue](experiment-catalogue.md): generated descriptions of scenarios, interventions, independent acceptance criteria and measurements.
3. [Measurement contract](measurement-contract.md): evidence ownership, privacy, hardware counters, token charges and reporting rules.
4. [Methodology](../docs/methodology.md): how task ability, mechanism tests and causal claims differ.
5. [Historical review](../docs/history/v6-evidence-review.md): limits of the previous evidence; its grades are not current results.
6. [Architecture tradeoff studies](architecture-studies.md): seven cross-dimensional studies, a three-study first wave, and preregistration requirements for explaining benefits, costs and design intent.
7. [First-wave pilot evidence](evidence/README.md): actual bounded execution on the installed OpenClaw build, retained observations and inference limits.
8. [Current stable campaign](current-version.md): resolve and pin the latest stable release, run it on a disposable hosted machine, and keep old harness-bootstrap evidence separate.
9. [Source-driven investigations](source-investigations.md): trace surprising results to implementation owners, challenge alternative explanations and execute discriminating interventions. This is the continuing work loop, not an optional narrative after a benchmark.

## Tooling

```sh
python3 evaluation/tools/check_design.py
python3 -m unittest discover -s evaluation/tests -v
python3 evaluation/tools/suite.py list
python3 evaluation/tools/suite.py plan --dimension observability
python3 evaluation/tools/suite.py plan --dimension resources_cost --phase real-model
python3 evaluation/tools/architecture.py plan --wave 1
```

`suite.py plan` emits `kind: plan-only`, `execution_enabled: false` and the selected OpenClaw cases. `--dimension` and `--case` can be repeated and intersect; unknown selectors and empty selections fail. The default `deterministic` phase excludes real usage. `--phase real-model` and `--phase all` select plans without contacting providers.

The schema checks OpenClaw-only scope, exactly six dimensions, essential coverage such as privacy and hooks, detailed resource metrics, phase requirements and all 46 legacy case mappings. IDs such as `REL-01` and `SEC-08` are current case IDs; `legacy_ids` only records provenance from the earlier design. Portability and operations cases now sit under reliability, scale under performance, and protocol integration under the appropriate six dimensions.

The catalogue is generated from the matrix:

```sh
python3 evaluation/tools/suite.py catalogue > evaluation/experiment-catalogue.md
python3 evaluation/tools/check_design.py
```

## Implementation sequence

The first-wave [native pilot adapter](runner/README.md) now provides isolated task state, build/configuration reporting, local provider/tool fixtures, independent receipt events, native-state inspection and resource sampling. Extend it toward the remaining deterministic authority, protocol and telemetry cases with independent fixture validation. Declare supported capabilities for the pinned runtime; unsupported hook points, transports, OS targets or deployment topologies remain explicit outcomes.

Then implement independently accepted task workloads and a separately budgeted real-model phase for task quality, prompt-injection susceptibility, long context and actual billing. Record provider/model settings to distinguish model behavior from framework behavior. The [measurement contract](measurement-contract.md) defines the accounting rules; `costs.py` calculates estimates from explicitly supplied usage and dated prices.

No aggregate grade is defined. Compare supported OpenClaw configurations or revisions within the same task contract when useful; no Hermes installation or paired-product result is required.

The first implementation milestone is the [three-study architecture wave](architecture-studies.md): cross-session capacity, sandbox ownership and plugin failure/authority. These compose existing cases rather than adding reporting dimensions. Preregister and observe benefits, costs and guardrails together; use boundary comparisons only for the inference they support.
