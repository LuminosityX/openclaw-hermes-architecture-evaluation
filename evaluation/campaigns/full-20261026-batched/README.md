# Formal OpenClaw campaign progress

The [active frozen plan](plan.json) has **139/257 scenarios completed**, with **570 independent observations**. 132 scenarios pass and 7 retain failure observations. Another 118 remain incomplete. Only accepted formal records count. Architecture interpretation remains deferred.

Native OpenClaw is pinned to `2026.10.7`, source `157d8c2bc3ea2fa183afdc11088e69690bf8e64e`. Each scenario completes its prescribed three or six independent units on disposable GitHub-hosted runners.

| Family | Completed scenarios | Independent observations | Hosted runs |
| --- | ---: | ---: | --- |
| REL-02 External effects and lost acknowledgments | 3 | 9 | [40323072237](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40323072237) |
| REL-04 Recovery automation and service availability | 4 | 12 | [40315477743](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40315477743), [40322602646](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40322602646) |
| REL-06 State identity under relocation | 4 | 12 | [40317319057](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40317319057) |
| REL-09 Credential and endpoint rebind | 4 | 12 | [40307698568](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40307698568) |
| REL-10 Consistent backup during active work | 4 | 12 | [40311076074](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40311076074), [40312921492](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40312921492) |
| REL-13 MCP session and cancellation lifecycle | 4 | 12 | [40311646155](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40311646155), [40312916295](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40312916295) |
| REL-14 Model streaming and reasoning payloads | 4 | 12 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| REL-15 Provider outages, timeouts and bounded retries | 5 | 15 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| SEC-01 Execution-surface authority | 5 | 15 | [40307698568](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40307698568), [40309312751](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40309312751) |
| SEC-03 Isolation setup and path races | 4 | 12 | [40308702865](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40308702865) |
| SEC-05 Policy resolution across entry points | 4 | 12 | [40324442544](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40324442544) |
| SEC-10 Network egress, SSRF and redirect boundaries | 5 | 15 | [40323668721](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40323668721) |
| SEC-11 Gateway and control-plane authentication | 5 | 15 | [40296866652](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40296866652) |
| PERF-01 Request preparation on the service path | 3 | 18 | [40306085535](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40306085535) |
| PERF-02 CPU work versus asynchronous waiting | 4 | 24 | [40306085535](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40306085535) |
| PERF-03 Tool scheduling and connection locks | 4 | 24 | [40323072237](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40323072237) |
| PERF-04 Fairness during a slow task | 4 | 24 | [40306085535](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40306085535), [40309012602](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40309012602) |
| PERF-05 Admission and overload behavior | 4 | 24 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| PERF-06 State contention under parallel sessions | 4 | 24 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| PERF-08 Sustained load and recycling | 4 | 24 | [40307698568](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40307698568) |
| PERF-09 Problem-solving ability on independently accepted tasks | 5 | 30 | [40291350809](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40291350809) |
| COST-01 Resident baseline and marginal session memory | 5 | 30 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| COST-02 Initialization and component reuse | 4 | 24 | [40306085535](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40306085535) |
| COST-04 Disk and inode amplification | 4 | 24 | [40306085535](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40306085535) |
| COST-06 Detailed hardware usage and cleanup accounting | 6 | 36 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| EXT-01 Extension replacement during active work | 4 | 12 | [40307698568](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40307698568) |
| EXT-05 MCP transport and content contracts | 4 | 12 | [40311646155](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40311646155) |
| EXT-06 AGENTS.md and external Skill inputs | 4 | 12 | [40309632222](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40309632222) |
| EXT-08 Hook ordering, mutation and error semantics | 6 | 18 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| EXT-09 Plugin composition and public architecture boundaries | 5 | 15 | [40289957217](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40289957217) |
| OBS-05 Diagnosis and operational burden | 4 | 12 | [40307698568](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40307698568) |
| OBS-07 Practical trace access, export and defect diagnosis | 6 | 18 | [40306085535](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40306085535), [40308089179](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40308089179) |

| Required dimension | Formal scenarios completed / planned |
| --- | ---: |
| reliability | 32 / 58 |
| security | 23 / 54 |
| performance | 32 / 41 |
| resources_cost | 19 / 33 |
| extensibility | 23 / 39 |
| observability | 10 / 32 |

Scenarios retaining failed acceptance observations: REL-06-S01, REL-06-S04, PERF-06-S02, PERF-06-S03, EXT-05-S04, OBS-05-S02, OBS-05-S04. These are execution results; source-backed architectural diagnosis remains deferred.

Passing conditions apply only to the declared fixtures, workload sizes, deadlines and hardware bounds. In particular, PERF-09 uses five synthetic task types with six variants each; it does not establish general task-solving ability.

SEC-11 follows its [registered wire protocol](security-protocol.md). It uses synthetic shared secrets and explicitly paired read-scoped device tokens, authenticating against the actual Gateway. All five scenarios complete three formal units with no real provider calls. The expiry condition specifically measures a stale signed device proof on reconnection. Origin and scope observations apply to the declared client paths and grants.

PERF-09 uses real `deepseek-flash` API calls with the official pinned provider plugin, thinking enabled, a 16,384 output-token ceiling per request, 16 protocol requests per task and a 180-second task deadline. Functional answers, citations and external effects are accepted independently of the model's final text. Correct artifacts alone cannot hide a missed deadline or native HTTP failure. Provider usage is recorded separately; actual invoiced charges remain unknown. The user has not set a campaign monetary ceiling.

The [provider accounting record](provider-usage-accounting.json) retains 163 real requests, 605,340 inclusive input tokens and 60,363 output tokens. Cache-hit input is 558,464 tokens and cache-miss input is 46,876; those partition input rather than add to it. All requests retain provider usage. These counters do not establish actual invoiced USD, immutable model weights or completion of COST-07.

## Evidence and cloud collection incident

The [compact result records](results/) bind the plan, runtime, controller commit, unit and original evidence. The [hosted evidence manifests](hosted-evidence/) bind original file hashes and artifact ZIP hashes. Original synthetic native records, task artifacts and provider usage remain in bounded hosted artifacts for 30 days. Local retention reads ZIPs in memory and stores no raw formal trajectory or runtime installation. The complete local campaign footprint remains below its 4 MiB limit.

The native batch's GitHub workflow is marked failed because the later collection step attempted to create a provenance directory inside root-owned controller output. All eight native execution steps, artifact uploads and cleanup steps succeeded. The saved `execution.json` files report no unit harness failures, and all 174 records bind the original native summary hashes. Root-level installation checks remain in each artifact; their dependency lock is retained in the repository. Commit `e1e6f2f` corrects collection ownership, and the subsequent real-model batch completes with the corrected workflow. Completed native experiments are retained rather than rerun to repair a collection-only failure. The original workflow conclusion remains visible in every evidence manifest.

Run `python3 evaluation/tools/campaign.py status` for the current audit. `seal` continues to reject the incomplete 257-scenario campaign. Previous preparation checks and pilots remain excluded.

## Validity exclusions and selective repairs

[Validity incidents](validity-incidents.json) document invalid early usage scoring, missed cancellation timing, an undocumented nonnull abort-ID assumption, and an MCP fixture callback omission. Invalid observations never count as product failures. Original hosted records are unchanged; compact manifests retain exclusions and hashes, with the normalized first cancellation-repair rows preserved in [quarantined-results](quarantined-results/). Only affected pending scenarios are repeated after whole-family native recalibration. Native usage polling and actual active cancellation now pass their replacement executions.
