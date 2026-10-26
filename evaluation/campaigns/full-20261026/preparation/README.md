# Full-campaign preparation evidence

These records validate configuration, native adapter wiring and independent acceptance. They are **not full-campaign observations**. The active [batched plan](../../full-20261026-batched/plan.json) reuses this preparation directory and still requires all 257 scenarios and their prescribed independent units before unified architecture analysis. The original plan remains unchanged as a scheduling snapshot.

| Check | Evidence | Meaning |
| --- | --- | --- |
| DeepSeek connection | [models discovery](../connection/deepseek-connection.json), [hosted run](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40280539151) | Authenticated `deepseek-flash` discovery; no completion requested |
| Native real-provider plumbing | [native record](model-harness-40281181126-native.json), [usage ledger](model-harness-40281181126-provider-usage.json), [hosted run](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40281181126) | Two real API calls, one independently committed tool effect; no task-quality or architecture claim |
| Protocol and hook adapter calibration | [REL-14](adapter-validation-40285210888-REL-14.json), [REL-15](adapter-validation-40285210888-REL-15.json), [EXT-08](adapter-validation-40285210888-EXT-08.json), [hosted run](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40285210888) | Fifteen single-unit scenario calibrations, deterministic local providers; full independent-unit requirements remain outstanding |
| Task delivery and hidden acceptance | [PERF-09 proof](adapter-validation-40285208020-PERF-09.json), [hosted run](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40285208020) | Five golden local transcripts validate native tools, artifacts, receipts and controller-side acceptance; zero real provider calls and no model-capability result |

The latest native cohort is [hosted run 40289234512](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289234512): REL-14, REL-15, EXT-08, PERF-05, PERF-06, COST-01, COST-06 and EXT-09, covering 39 candidate scenarios. Native product failures remain in the original records and do not invalidate a correctly exercised fixture. The current [golden task proof](adapter-validation-40290494698-PERF-09.json) verifies five task adapters including formal-purpose/deadline checks, with zero real provider calls.

The current cohort validates 44 candidate scenarios against matching controller hashes; 213 still require implementation. New [formal batches](../../full-20261026-batched/README.md) separately complete those 44 scenarios and 204 independent observations, including 30 real-model task runs. None of the preparation records here is promoted into formal coverage.

The real-provider plumbing check returned 4,613 inclusive input tokens, 74 output tokens and 2,176 cache-hit input tokens across its two calls. Cache tokens are part of input, not additional input. Provider-reported USD and invoice reconciliation remain unknown. The selected model alias does not establish immutable model weights.

The task golden controls intentionally supply correct deliverables. They prove that the native delivery and independent acceptance path can work; they cannot establish whether a real model solves those tasks. Generated solution functions are checked in a separate hosted mount/PID/network/cgroup boundary. The oracle's expected answers and provider key remain outside the agent namespace. Controller validation preserves failed outcomes, unknown usage and immutable-input checks.

## Calibration failures and corrections

- [Initial mount failure](model-harness-40280942578-native.json): the namespace could not traverse a hosted installation path; no Gateway/model task ran. The verified hosted mount profile corrected the fixture.
- `40281929634` REL-14/REL-15 records: a Unicode test token was incorrectly placed in an HTTP header. No provider request was reached. Session/call identifiers now use ASCII hashes while Unicode remains in the JSON arguments being tested.
- `40282384451` EXT-08-S03 used an invalid acceptance assumption: a persistence hook was required to rewrite the current live provider request. The corrected adapter checks the native persisted transcript separately.
- `40282384451` REL-14-S04 applied DeepSeek-specific reasoning replay expectations to a generic provider. The corrected adapter loads the pinned official DeepSeek plugin and its documented reasoning-enabled condition.
- `40289960625` reached native task completion but the new deadline assertion read a public-spec field from the host workload's wrong level, raising `KeyError`. Commit `231d7a4` reads the actual host workload schema; `40290494698` revalidated all five golden scenarios before paid formal execution.

These are preparation issues, not completed full-campaign product failures. The original records remain auditable. Newer calibration evidence does not retroactively change those records or count them toward the frozen campaign.

`adapter_readiness.py` accepts a preparation proof only when its required controller hashes still match. Later code/fixture changes therefore require recalibration; historical green jobs do not automatically establish current readiness.

## Dependency and storage provenance

The real-provider plumbing installation uses the existing shared [dependency lock](../../../evidence/current-stable-20261026/package-lock-005ded4ea9b1.json), SHA-256 `005ded4ea9b1b00d511834d8bba98076d9777fd61cf8e7f1a53f61c11fe1a76b`. Per-run installation manifests retain the installed release identity. Calibrations using the official provider retain one additional common dependency lock and per-run provider verification; runtime installations and caches were deleted on the hosted runners.

Only bounded synthetic JSON and dependency metadata are retained here. No API key, local runtime installation, dependency tree, state database or raw private trajectory is retained. Download transport directories are removed after bounded evidence retention. The complete campaign's local evidence ceiling remains 4 MiB.
