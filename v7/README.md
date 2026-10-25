# V7 architecture evaluation design

**Status: design draft. No V7 product experiments have been executed.**

The `main` branch preserves the V6 source archive at commit `a33644efc9490ff771d058ebf047f08550e4ccb3`. This research branch adds a separate evaluation design without modifying any file under `v6/`.

## Start here

1. [V6 review](review-v6.md): what the existing tests establish, what they leave open, and where the architecture interpretation exceeded the evidence.
2. [Measurement contract](measurement-contract.md): experimental units, causal controls, outcome axes, and storage constraints.
3. [Experiment catalogue](experiment-catalogue.md): 46 proposed experiment families across all eleven dimensions.
4. [Evaluation matrix](design/evaluation-matrix.json): machine-readable mechanisms, interventions, scenarios, oracles, and metrics.

The catalogue contains 182 scenario labels. These are planning entries, not 182 executable cases or completed runs. Each family still needs a validated fixture, matched product adapters, and a predeclared sampling plan.

## Offline validation

```sh
python3 tools/check_repository.py
python3 v7/tools/check_design.py
```

These commands validate archive integrity, the existing scorer, and design consistency. They do not establish product results or enable experiment execution. The matrix disables dependency downloads and paid model calls.

## Implementation order

- First implement independent task, authorization, side-effect, and resource ledgers plus deterministic local fixtures. Validate their own failure behavior before testing products.
- Implement durability and effect-acknowledgment tests, policy revocation races, execution-surface isolation, and preparation-time attribution. These distinguish the architectural explanations most likely to be overstated.
- Add overload, sustained load, dependency publication, and collector durability tests with explicit disk and duration limits.
- Complete protocol conformance and native migration only on actually available executors. Add separately budgeted real-model confirmation where deterministic fixtures cannot answer the question.

No new aggregate product grade is defined here. First establish the mechanisms and outcome boundaries; pre-register any later aggregation before examining V7 comparative outcomes.
