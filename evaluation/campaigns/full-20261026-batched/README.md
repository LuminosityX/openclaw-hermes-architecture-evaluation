# Formal OpenClaw campaign progress

The [active frozen plan](plan.json) currently has **44/257 scenarios completed**, with **204 independent observations**. Forty-two scenarios pass and two have failure observations. Another 213 scenarios still need implementation and execution. The entire campaign is incomplete and architecture interpretation remains deferred.

These are new formal executions, separate from the [development calibration](../full-20261026/preparation/README.md). Each scenario completed its prescribed three or six independent units. Native OpenClaw is pinned to `2026.10.7`, source `157d8c2bc3ea2fa183afdc11088e69690bf8e64e`, with one full dependency lock shared across formal shards. Every hosted job deletes its owned installation, cache and runtime state.

| Family | Completed scenarios | Independent observations | Hosted run |
| --- | ---: | ---: | --- |
| REL-14 streaming/reasoning payloads | 4 | 12 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| REL-15 provider errors/timeouts/retries | 5 | 15 | same native batch |
| PERF-05 admission and bounded queueing load | 4 | 24 | same native batch |
| PERF-06 parallel-session state contention | 4 | 24 | same native batch |
| COST-01 baseline/session memory | 5 | 30 | same native batch |
| COST-06 hardware and cleanup accounting | 6 | 36 | same native batch |
| EXT-08 hooks | 6 | 18 | same native batch |
| EXT-09 plugin composition | 5 | 15 | same native batch |
| PERF-09 independently accepted task delivery | 5 | 30 | [40291350809](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40291350809) |

| Required dimension | Formal scenarios completed / planned |
| --- | ---: |
| Reliability | 9 / 58 |
| Security/privacy/network | 0 / 54 |
| Performance/task ability | 13 / 41 |
| Resources/cost | 11 / 33 |
| Extensibility | 11 / 39 |
| Observability | 0 / 32 |

PERF-06-S02 and PERF-06-S03 each retain failure observations across all six units. This is an execution status, not a source-backed architectural diagnosis. Passing conditions apply only to the declared fixtures, workload sizes, deadlines and hardware bounds. In particular, PERF-09 uses five synthetic task types with six variants each; it does not establish general task-solving ability.

PERF-09 uses real `deepseek-flash` API calls with the official pinned provider plugin, thinking enabled, a 16,384 output-token ceiling per request, 16 protocol requests per task and a 180-second task deadline. Functional answers, citations and external effects are accepted independently of the model's final text. Correct artifacts alone cannot hide a missed deadline or native HTTP failure. Provider usage is recorded separately; actual invoiced charges remain unknown. The user has not set a campaign monetary ceiling.

The [provider accounting record](provider-usage-accounting.json) retains 163 real requests, 605,340 inclusive input tokens and 60,363 output tokens. Cache-hit input is 558,464 tokens and cache-miss input is 46,876; those partition input rather than add to it. All requests retain provider usage. These counters do not establish actual invoiced USD, immutable model weights or completion of COST-07.

## Evidence and cloud collection incident

The [compact result records](results/) bind the plan, runtime, controller commit, unit and original evidence. The [hosted evidence manifests](hosted-evidence/) bind original file hashes and artifact ZIP hashes. Original synthetic native records, task artifacts and provider usage remain in bounded hosted artifacts for 30 days. Local retention reads ZIPs in memory and stores no raw formal trajectory or runtime installation. The complete local campaign footprint remains below its 4 MiB limit.

The native batch's GitHub workflow is marked failed because the later collection step attempted to create a provenance directory inside root-owned controller output. All eight native execution steps, artifact uploads and cleanup steps succeeded. The saved `execution.json` files report no unit harness failures, and all 174 records bind the original native summary hashes. Root-level installation checks remain in each artifact; their dependency lock is retained in the repository. Commit `e1e6f2f` corrects collection ownership, and the subsequent real-model batch completes with the corrected workflow. Completed native experiments are retained rather than rerun to repair a collection-only failure. The original workflow conclusion remains visible in every evidence manifest.

Run `python3 evaluation/tools/campaign.py status` for the current audit. `seal` continues to reject the incomplete 257-scenario campaign. Previous preparation checks and pilots remain excluded.
