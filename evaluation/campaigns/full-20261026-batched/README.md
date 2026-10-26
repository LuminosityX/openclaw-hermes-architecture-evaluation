# Formal OpenClaw campaign progress

The [active frozen plan](plan.json) currently has **83/257 scenarios completed**, with **378 independent observations**. 81 scenarios pass and 2 retain failure observations. Another 174 scenarios remain incomplete. Running batches and missing implementations are not counted. Architecture interpretation remains deferred.

These are new formal executions, separate from the [development calibration](../full-20261026/preparation/README.md). Each scenario completed its prescribed three or six independent units. Native OpenClaw is pinned to `2026.10.7`, source `157d8c2bc3ea2fa183afdc11088e69690bf8e64e`, with one full dependency lock shared across formal shards. Every hosted job deletes its owned installation, cache and runtime state.

| Family | Completed scenarios | Independent observations | Hosted runs |
| --- | ---: | ---: | --- |
| REL-14 Model streaming and reasoning payloads | 4 | 12 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| REL-15 Provider outages, timeouts and bounded retries | 5 | 15 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| SEC-01 Execution-surface authority | 1 | 3 | [40309312751](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40309312751) |
| SEC-03 Isolation setup and path races | 4 | 12 | [40308702865](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40308702865) |
| SEC-11 Gateway and control-plane authentication | 5 | 15 | [40296866652](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40296866652) |
| PERF-01 Request preparation on the service path | 3 | 18 | [40306085535](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40306085535) |
| PERF-02 CPU work versus asynchronous waiting | 4 | 24 | [40306085535](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40306085535) |
| PERF-04 Fairness during a slow task | 4 | 24 | [40306085535](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40306085535), [40309012602](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40309012602) |
| PERF-05 Admission and overload behavior | 4 | 24 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| PERF-06 State contention under parallel sessions | 4 | 24 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| PERF-09 Problem-solving ability on independently accepted tasks | 5 | 30 | [40291350809](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40291350809) |
| COST-01 Resident baseline and marginal session memory | 5 | 30 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| COST-02 Initialization and component reuse | 4 | 24 | [40306085535](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40306085535) |
| COST-04 Disk and inode amplification | 4 | 24 | [40306085535](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40306085535) |
| COST-06 Detailed hardware usage and cleanup accounting | 6 | 36 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| EXT-06 AGENTS.md and external Skill inputs | 4 | 12 | [40309632222](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40309632222) |
| EXT-08 Hook ordering, mutation and error semantics | 6 | 18 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| EXT-09 Plugin composition and public architecture boundaries | 5 | 15 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| OBS-07 Practical trace access, export and defect diagnosis | 6 | 18 | [40306085535](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40306085535), [40308089179](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40308089179) |

| Required dimension | Formal scenarios completed / planned |
| --- | ---: |
| reliability | 9 / 58 |
| security | 10 / 54 |
| performance | 24 / 41 |
| extensibility | 15 / 39 |
| observability | 6 / 32 |

PERF-06-S02 and PERF-06-S03 each retain failure observations across all six units. This is an execution status, not a source-backed architectural diagnosis. Passing conditions apply only to the declared fixtures, workload sizes, deadlines and hardware bounds. In particular, PERF-09 uses five synthetic task types with six variants each; it does not establish general task-solving ability.

SEC-11 follows its [registered wire protocol](security-protocol.md). It uses synthetic shared secrets and explicitly paired read-scoped device tokens, authenticating against the actual Gateway. All five scenarios complete three formal units with no real provider calls. The expiry condition specifically measures a stale signed device proof on reconnection. Origin and scope observations apply to the declared client paths and grants.

PERF-09 uses real `deepseek-flash` API calls with the official pinned provider plugin, thinking enabled, a 16,384 output-token ceiling per request, 16 protocol requests per task and a 180-second task deadline. Functional answers, citations and external effects are accepted independently of the model's final text. Correct artifacts alone cannot hide a missed deadline or native HTTP failure. Provider usage is recorded separately; actual invoiced charges remain unknown. The user has not set a campaign monetary ceiling.

The [provider accounting record](provider-usage-accounting.json) retains 163 real requests, 605,340 inclusive input tokens and 60,363 output tokens. Cache-hit input is 558,464 tokens and cache-miss input is 46,876; those partition input rather than add to it. All requests retain provider usage. These counters do not establish actual invoiced USD, immutable model weights or completion of COST-07.

## Evidence and cloud collection incident

The [compact result records](results/) bind the plan, runtime, controller commit, unit and original evidence. The [hosted evidence manifests](hosted-evidence/) bind original file hashes and artifact ZIP hashes. Original synthetic native records, task artifacts and provider usage remain in bounded hosted artifacts for 30 days. Local retention reads ZIPs in memory and stores no raw formal trajectory or runtime installation. The complete local campaign footprint remains below its 4 MiB limit.

The native batch's GitHub workflow is marked failed because the later collection step attempted to create a provenance directory inside root-owned controller output. All eight native execution steps, artifact uploads and cleanup steps succeeded. The saved `execution.json` files report no unit harness failures, and all 174 records bind the original native summary hashes. Root-level installation checks remain in each artifact; their dependency lock is retained in the repository. Commit `e1e6f2f` corrects collection ownership, and the subsequent real-model batch completes with the corrected workflow. Completed native experiments are retained rather than rerun to repair a collection-only failure. The original workflow conclusion remains visible in every evidence manifest.

Run `python3 evaluation/tools/campaign.py status` for the current audit. `seal` continues to reject the incomplete 257-scenario campaign. Previous preparation checks and pilots remain excluded.

## Validity exclusions and selective repairs

[Validity incidents](validity-incidents.json) document invalid early usage scoring, missed cancellation timing, an undocumented nonnull abort-ID assumption, and an MCP fixture callback omission. Invalid observations never count as product failures. Original hosted records are unchanged; compact manifests retain exclusions and hashes, with the normalized first cancellation-repair rows preserved in [quarantined-results](quarantined-results/). Only affected pending scenarios are repeated after whole-family native recalibration. Native usage polling and actual active cancellation now pass their replacement executions.
