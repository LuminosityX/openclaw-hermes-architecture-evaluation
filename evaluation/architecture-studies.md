# Architecture tradeoff studies

The six dimensions remain the reporting axes. The 60 case families remain the coverage inventory. Seven architecture studies compose those cases around a design mechanism, so the same workload can expose both benefits and costs. They are not additional dimensions. The [study specification](design/architecture-studies.json) remains the confirmatory plan; its selector does not enable execution. An explicitly invoked [bounded native runner](runner/README.md) now implements first-wave exploratory pilots. Pilot execution does not complete every scenario or certify a tradeoff.

## Questions and first wave

| Order | Study | Controlled change or boundary | Proposed benefit | Possible cost | Inference limit |
| --- | --- | --- | --- | --- | --- |
| 1 | ARC-01 Session ordering/concurrency | Change supported cross-session capacity with fixed independent sessions | Useful throughput with correct session ordering | Peak resources, queue tails and upstream pressure | Does not disable or prove the optimality of session serialization |
| 2 | ARC-03 Sandbox ownership | Agent-scoped versus session-scoped tool sandbox, other grants and mounts fixed | Less unintended writable-state sharing | Startup, memory, disk/inodes and cleanup | Does not establish hostile-user isolation or confine host plugins |
| 3 | ARC-02 Plugin failure/authority | Equivalent tool effect via in-process plugin versus supported external process | Integration access or fewer handoffs | Wider authority and shared Gateway fault scope | A boundary comparison; transport and interface differences prevent a pure isolation-cost claim |
| Later | ARC-04 Tracing | One supported native detail/export setting at a time | Better blind fault diagnosis | Collection overhead, retention and privacy | Hold redaction/retention fixed; unsupported controls block the contrast |
| Later | ARC-05 Context reuse | One supported reuse component | Amortized tokens/time at accepted quality | Stale context, retained private data, setup cost | Requires real models, matched task sequences and rule-change reversals |
| Later | ARC-06 Retries | One supported native retry allowance | Transient-failure recovery | Extra calls, latency and replay risk | Hold idempotency and deadlines fixed; local counts are not actual USD |
| Later | ARC-07 Gateway ownership | Shared versus separate supported deployments | Resident-resource and integration reuse | Shared contention and failure scope | A topology comparison, not an ablation of internal Gateway architecture |

Current public documentation describes [session queues](https://docs.openclaw.ai/concepts/queue), [trusted in-process plugins and sandbox scopes](https://docs.openclaw.ai/gateway/security/tool-permissions), and [Gateway ownership](https://docs.openclaw.ai/concepts/architecture). Those references guide hypotheses; they are not verification of an unspecified installed runtime. Bind every mechanism and config key to the pinned source before executing. The queue's collision-avoidance objective is documented; the proposed performance motives for plugins and other choices remain hypotheses unless separate design evidence is found.

## Work in this order

1. Pin one OpenClaw build, record the observed installed version/source commit and effective configuration, and map ingress/auth, routing, session queue, agent execution, tools/plugins, state/effects and tracing to actual source and process boundaries. Record which claims are documented goals, inferred mechanisms or untested hypotheses. Do not start a broad benchmark against an unidentified installation.
2. Implement a minimal deterministic OpenClaw adapter plus an owned local tool/effect server, scripted provider endpoint, task/event ledger and resource collector. Validate the fixtures independently, including deliberate bad behavior and collector loss. A harness-owned queue, retry or sandbox cannot stand in for the product mechanism under test.
3. Use ARC-01 first to validate admission/dispatch/task correlation and the collector. Then implement ARC-03 for creation/reuse/cleanup boundaries, followed by ARC-02 for plugin authority and failure propagation. These first-wave studies do not need paid model calls. If the pinned product lacks an external tool route or sandbox backend, mark that contrast unsupported rather than synthesizing native support.
4. Pilot to estimate variability, then preregister workload/reversal revisions, independent paired blocks, sample-size rationale, estimands, uncertainty analysis, meaningful-difference/guardrail margins, stop rules and resource budgets. Pilot observations and confirmatory evidence remain separate. Randomize block order, reset owned state, and separate cold and warm conditions.
5. For each arm, observe all six axes in the same run. Explicitly explain non-applicable axes rather than manufacturing values. Keep native trajectories and independent effect truth separate, retain every attempt, then verify evidence before attributing differences to the mechanism.
6. Only after the adapter and first wave are independently validated, add real task capability, model-dependent attacks, context reuse and billed costs. Keep model/provider/settings fixed in matched blocks. No previous controller or preregistration file authorizes model spending by itself.

## A concrete first experiment

For ARC-01, keep a fixed number of independent sessions and the same task arrivals, tool effects and deterministic provider transcript. Compare a verified native cross-session capacity of one versus four, only if supported at the pinned revision. Record state/effect correctness, goodput, completion/queue latency, CPU/memory peaks, authority violations and trace linkage together. Saturate the system with independently controlled slow tools and short tasks to find where gains reverse.

Do not change from one session to several sessions at the same time. That changes the contention boundary. A separate same-session workload may reveal why serialization exists, but it does not by itself establish that disabling it would improve the architecture. A private patch that removes serialization would be a separately identified counterfactual, with its own source and evidence.

For ARC-03, keep image, backend, sandbox mode, mounts, network rules and effective grants fixed; change only verified sandbox scope. Include allowed-operation controls and unique synthetic workspace canaries. Separate intentional shared mounts from unexpected sandbox-state reach, and compare per-session startup/cleanup resources. More containers without reduced unintended reach establishes a cost, not a demonstrated security benefit.

For ARC-02, hold the tool's observable effect contract and payload fixed while comparing supported routes. Record all route differences, hook coverage and failure owners. Blocking the Gateway through a plugin can reveal a shared fault domain, but a lower call count or latency in the same experiment is still associated with several route differences. Do not claim process isolation alone caused the whole difference.

## Plans and preregistration tooling

```sh
python3 evaluation/tools/architecture.py plan --wave 1
python3 evaluation/tools/architecture.py plan --study ARC-03
python3 evaluation/tools/architecture.py template --study ARC-01 > /absolute/path/arc-01-registration.json
python3 evaluation/tools/architecture.py check-registration /absolute/path/arc-01-registration.json
```

The generated template is intentionally incomplete and fails readiness checks. Populate the observed target, stable flattened effective configurations, sample design, uncertainty method, workload and reversal revisions, meaningful-difference margins in the matrix's metric units, stop rules and whole-study budgets. Native contrasts must change exactly the declared config field. Two-arm independent unit counts must equal the number of paired blocks; more observations inside a block do not increase that count. This bookkeeping does not certify sample-size adequacy.

Attach absolute paths and SHA-256 hashes for `runtime_identity`, `source_binding`, both effective configs, fixture/collector self-tests, owned resource manifest and analysis plan. Runtime identity is JSON containing `product`, `version`, and `source_commit` matching the preregistration. The source-binding JSON contains `product`, `study_id`, `source_commit`, `mechanism_supported: true`, and nonempty `source_locations` at that revision; native config studies also bind `config_key`. Review that evidence independently. A supported mechanism does not prove a hypothesized design goal.

The checker verifies metadata completeness, single-field declarations, target consistency and artifact bytes. It does not prove that artifacts truthfully describe a runtime, that a fixture or statistical method is valid, or that execution is authorized. Even a valid record returns `execution_enabled: false` and `product_results_verified: false`. The plan/preregistration commands do not start OpenClaw, inject faults or contact a model provider; actual exploratory execution uses the separately invoked bounded runner.

## Reporting a conclusion

Use one evidence chain per mechanism: documented goal or explicit hypothesis, pinned implementation, observed symptom, controlled contrast or boundary comparison, measured benefit and cost, uncertainty, confounders, and workloads where the result reverses. Report unmeasured axes, missing evidence and counterfactual patches explicitly. A diagram and source reading help explain ownership; neither replaces an executed task.

Classify findings as configuration problem, implementation defect, architectural constraint, measured tradeoff, workload mismatch, or inconclusive. These are reviewed interpretations, not labels automatically emitted from tool success or a metric sign. A defect can coexist with a legitimate architectural tradeoff and still deserve a fix.

A measured tradeoff requires evidence of both a benefit and a cost. A performance deficit with no demonstrated compensating benefit remains an unexplained deficit. An alternative improving one axis without meaningful harm to the other measured axes is a candidate implementation improvement, not evidence that sacrifice was necessary. Failure to observe harm does not establish equivalence; report uncertainty and the preregistered margins. Even an observed tradeoff is limited to tested alternatives and does not prove a globally optimal design.

Check documented promises separately from workload suitability. A trusted-plugin model can be unsuitable for hostile extensions without being a sandbox bypass; an actual bypass of a promised boundary is still a defect. Infer design intent only from version-appropriate documentation, design records or explicit maintainer evidence, keeping that claim distinct from experimental behavior.
