# Codex campaign: 60-family mechanism mapping

This table translates every experiment family of the frozen six-dimension design
([evaluation-matrix.json](evaluation-matrix.json), OpenClaw campaign) to Codex
`0.164.0` (commit `6aaac694803004a63c6f393d153c96d22521a6b9`,
[codex-target-pin.json](codex-target-pin.json)). It preserves all 60 families
and all 257 scenario slots. Scenario counts per family never change; only the
mechanism, intervention and oracle are expressed against Codex surfaces.

Classes:

- **A — direct map**: the Codex mechanism is equivalent; the controller drives a
  corresponding native surface and keeps the original acceptance intent.
- **B — equivalent rewrite**: the capability exists but under a different
  contract; scenarios are rewritten against the Codex contract while preserving
  the family's acceptance question.
- **C — probe first**: expected native nonapplicability or conditional
  applicability; requires an actual native probe plus a pinned support-contract
  reference before it can be labelled `unsupported` (never a silent skip).

Source references use `codex-rs/` crate paths at the pinned commit. Protocol
methods refer to the `codex app-server` JSON-RPC surface captured by
`generate-json-schema` at the same commit (106 client methods).

## Reliability (15 families, 58 scenarios)

| Family | Class | Codex mechanism | Mapping notes |
| --- | --- | --- | --- |
| REL-01 Admission and persistence boundaries | A | `thread/start` + `turn/start` acknowledgment vs rollout JSONL flush (`codex-rs/rollout`, recorder + `reverse_jsonl_scanner`) | Kill boundaries: before rollout append, after append before turn completion event, after completion before client response. Restart via `thread/resume`. |
| REL-02 External effects and lost acknowledgments | A | Tool/shell external effects vs turn completion; delayed-commit effect fixture | Same delayed-commit oracle: effect visible in the independent ledger before Codex acknowledges completion. |
| REL-03 Delegated work and stale owners | B | `thread/fork` delegation; `app-server-daemon` shared-owner model | Stale-daemon arm: kill client, keep daemon; second client attaching to the same thread. No lease protocol equivalent is assumed; probe whether a stale owner blocks a new writer. |
| REL-04 Recovery automation and service availability | B | Daemon restart + `thread/resume`; `codex exec resume` | Service availability measured on the app-server control path, not a HTTP gateway. |
| REL-05 Cancellation across descendants | A | `turn/interrupt`, `turn/steer`, `command/exec/terminate` | Descendants = sandboxed child processes of a running command; check actual process trees after interrupt. |
| REL-06 State identity under relocation | B | `CODEX_HOME` relocation; `session_index.jsonl`, `state_5.sqlite`, `thread_history_1.sqlite` | Scenario names rewritten (state-path-only / combined relocation) around moving an owned CODEX_HOME mid-lifecycle and resuming threads. |
| REL-07 Dependency reconstruction without host leakage | B | Rebuild config.toml + auth + MCP servers + skills in a fresh CODEX_HOME from repo-owned inputs only | Host leakage = references escaping the isolated home (absolute paths into the host user's real state). |
| REL-08 Native cross-OS semantics | C | Linux runners only in this campaign: `windows-sandbox-rs`/`windows-sandbox-service` exist but are not exercised | Windows arms require a Windows hosted runner decision; without it those scenarios are probe-verified conditional nonapplicability, mirroring the OpenClaw disclosure pattern. Unicode/path arms run on Linux. |
| REL-09 Credential and endpoint rebind | A | `model_providers` base_url rebind; `auth.json`; `account/login/start`, `ChatgptAuthTokensRefresh`, `account/logout` | Rebind a provider endpoint mid-campaign and observe retry/re-auth behavior with synthetic credentials. |
| REL-10 Consistent backup during active work | A | Backup of owned CODEX_HOME (rollout files + SQLite + config) during an active turn | WAL-mode SQLite consistency check on restore; same partial-copy oracle as the OpenClaw family. |
| REL-11 Upgrade and rollback after partial migration | B | `codex migrate-rollouts` (legacy → paginated thread history), `codex migrate-nfs-db`; version skew 0.163→0.164 | Interrupt migration at real boundaries; rollback via reinstalling the older pinned binary against the same home. |
| REL-12 Dependency publication and repair | B | `plugin/install` + `plugin/reconcile`; `config/mcpServer/reload` | Repair = recovering a broken plugin/MCP registration from its published inputs without host state. |
| REL-13 MCP session and cancellation lifecycle | A | `mcpServer/tool/call`, `mcpServerStatus/list`; `codex-rs/rmcp-client` | MCP server restart mid-session; cancellation of an in-flight MCP call via turn interrupt. |
| REL-14 Model streaming and reasoning payloads | A | Responses-API streaming through a local fixture provider (`wire_api = responses`) | Reasoning summaries, partial deltas, malformed stream frames; same acceptance structure. |
| REL-15 Provider outages, timeouts and bounded retries | A | Fixture provider injecting 5xx/timeouts/hangs | Bounded retry observation on the real request path; usage ledger records every upstream request. |

## Security (12 families, 54 scenarios)

| Family | Class | Codex mechanism | Mapping notes |
| --- | --- | --- | --- |
| SEC-01 Execution-surface authority | A | `SandboxMode` (read-only / workspace-write / danger-full-access / external-sandbox, `config/src/config_requirements.rs`), `execpolicy` rule engine, approval flows | Positive/negative probes per mode: file writes, network, process spawn outside grants. |
| SEC-02 Credential propagation and revocation | B | `auth.json`, provider `env_key`, `account/logout`, secrets crate propagation to tools | Which credential material reaches sandboxed commands; revocation effect on already-running turns. |
| SEC-03 Isolation setup and path races | A | workspace-write writable roots; `codex-rs/sandboxing` | Path races: symlink/TOCTOU against writable-root enforcement on the native Linux sandbox. |
| SEC-04 Cross-session authority separation | A | Two threads in one CODEX_HOME; `thread/list/read`, history access | Whether a restricted thread can read another thread's transcript or workspace artifacts. |
| SEC-05 Policy resolution across entry points | A | `config.toml` vs `-c` overrides vs `-p profile` vs app-server `config/batchWrite` | Effective-policy resolution matrix; same resolution-order oracle structure. |
| SEC-06 Revocation between approval and dispatch | A | `ExecCommandApproval`/`ApplyPatchApproval`/`FileChangeRequestApproval`/`PermissionsRequestApproval` server requests | Revoke/change policy between approval emission and actual dispatch; effect timeline oracle. |
| SEC-07 OAuth authorization lifecycle | B | `account/gatewayOAuth/login/cancel/read`, `mcpServer/oauth/login`, token refresh | Synthetic OAuth fixture against the real client paths (no real accounts). |
| SEC-08 User privacy across storage, logs, exports and deletion | A | `secrets/sanitizer`, rollout content, `logs_2.sqlite`, `history.jsonl`, `thread/delete` | Canary sweep across every persisted sink + deletion completeness. |
| SEC-09 Indirect prompt injection and data exfiltration | A | Real-model phase; same injection workloads (`evaluation/tools/injection_workloads.py`) | Untrusted content in repo files/skills/MCP results; exfiltration watched by the owned egress fixture. |
| SEC-10 Network egress, SSRF and redirect boundaries | A | `codex-rs/network-proxy`, sandbox network policy, workspace-write egress mode | Owned loopback fixtures; DNS/redirect/metadata-stand-in probes. |
| SEC-11 Gateway and control-plane authentication | B | app-server control socket; `remote-control` daemon; `codex-rs/websocket-auth` | Control-plane = the local app-server daemon and its transport; unauthenticated/unauthorized client probes against the real socket. |
| SEC-12 Untrusted extension installation and update | A | `plugin/install`, `marketplace/add/upgrade`, plugin manifest (`codex-rs/plugin/manifest.rs`) | Untrusted marketplace source; manifest tampering; update swap under an active thread. |

## Performance (10 families, 41 scenarios)

| Family | Class | Codex mechanism | Mapping notes |
| --- | --- | --- | --- |
| PERF-01 Request preparation on the service path | B | `turn/start` → first event decomposition via ServerNotification timeline | Same latency-attribution question on the app-server path. |
| PERF-02 CPU work versus asynchronous waiting | A | Deterministic fixture provider; CPU-bound vs IO-bound tool scripts | Unchanged from the OpenClaw design. |
| PERF-03 Tool scheduling and connection locks | B | Parallel tool calls; `command/exec` multiplexing; thread-writer locks (`CODEX_HOME/thread-writer-locks`) | Serialization points observed via latency coupling between neighbors. |
| PERF-04 Fairness during a slow task | A | Two concurrent threads; one blocked tool call | Neighbor responsiveness oracle. |
| PERF-05 Admission and overload behavior | B | Concurrent `turn/start` across threads; `queue_1.sqlite` queue behavior | Finite batch conditions copied from the frozen plan (8 requests / declared slots). |
| PERF-06 State contention under parallel sessions | A | SQLite WAL contention across threads; owned long-transaction fixture | Same one-second-held-transaction + rollback fixture against the real state DB. |
| PERF-07 Actual multi-host execution | C | `cloud-tasks`, `exec-server`, `codex cloud` are cloud-product surfaces, not a self-hosted node-dispatch contract | Probe first: if no self-hosted multi-host dispatch exists at this commit, record verified nonapplicability with the pinned contract; do not substitute the cloud product for a local mechanism. |
| PERF-08 Sustained load and recycling | A | Repeated turns; daemon stop/start cycles | Sustained-capacity oracle unchanged. |
| PERF-09 Problem-solving ability on independently accepted tasks | A | Real-model phase: same five synthetic task types × six variants, hidden host-side acceptance | Identical workloads and acceptance; only the harness differs. |
| PERF-10 Long-context and multi-turn task completion | A | Long threads; `thread/compact/start` (`rollout/src/compression`) | Compaction is a native Codex capability on the measured path. |

## Resource usage and cost (7 families, 33 scenarios)

| Family | Class | Codex mechanism | Mapping notes |
| --- | --- | --- | --- |
| COST-01 Resident baseline and marginal session memory | A | `codex exec` per-invocation and daemon-resident process trees | Same RSS/PSS/cgroup sampling contract. |
| COST-02 Initialization and component reuse | A | Cold exec vs warm daemon; plugin/skill load amortization | Unchanged. |
| COST-03 Learning and context cost amortization | B | Thread resume + compact; token usage across a long sequence | Same twenty-later-tasks oracle with Codex context management. |
| COST-04 Disk and inode amplification | A | Rollout files + SQLite growth per turn/thread | Unchanged. |
| COST-05 Concurrent budget enforcement | C | No known native concurrent-execution budget at this commit; `account/rateLimits/read` is account rate limiting, not a local budget | Probe first; expected verified nonapplicability exactly like the OpenClaw campaign (same family, same disclosure). |
| COST-06 Detailed hardware usage and cleanup accounting | A | cgroup-scoped accounting; `thread/delete`, `codex delete` cleanup completeness | Unchanged. |
| COST-07 Provider usage and actual token charge reconciliation | A | Response usage fields + `account/usage/read` + fixture-provider ledger | Same lost-reply/retry arm (upstream completes, response dropped). |

## Extensibility (9 families, 39 scenarios)

| Family | Class | Codex mechanism | Mapping notes |
| --- | --- | --- | --- |
| EXT-01 Extension replacement during active work | B | `plugin/install`/`uninstall` + `config/mcpServer/reload` during an active thread | Same replacement-under-active-work acceptance. |
| EXT-02 Full harness replacement versus provider routing | B | `model_providers` custom routing (`wire_api` responses/chat) vs `codex mcp` as an external harness | Wrapper-execution evidence equivalent (provider hook actually invoked). |
| EXT-03 Extension API and version skew | B | Plugin manifest versioning; old-plugin vs new-plugin across 0.163/0.164 binaries | Real old/new product pair, same as the OpenClaw family used. |
| EXT-04 Context and persistence contracts | B | `thread/compact/start`; `context-fragments`; `message-history` crates | Reference-component equivalent: does a compacting component satisfy the continuation contract. |
| EXT-05 MCP transport and content contracts | A | `mcpServer/tool/call`, rmcp-client; stdio + streamable-HTTP fixtures | Same text/structured/resource/Unicode/large-result matrix. |
| EXT-06 AGENTS.md and external Skill inputs | A | `docs/agents_md.md` contract; `skills` crate; `skills/list`, `skills/config/write`, `plugin/skill/read` | Direct native equivalents. |
| EXT-07 External tools, plugins, and harnesses | A | Plugin system + `codex mcp` external harness | Unchanged intent. |
| EXT-08 Hook ordering, mutation and error semantics | B | `plugin/src/bundled_hooks.rs`, `hooks/list` | Probe the native hook set first; ordering/mutation/error arms are then expressed against it. If the public hook surface is narrower than OpenClaw's, record the supported subset and mark the rest conditional. |
| EXT-09 Plugin composition and public architecture boundaries | A | Two plugins, different versions, public manifest API only | Same composition oracle (no core edits, no private imports). |

## Observability (7 families, 32 scenarios)

| Family | Class | Codex mechanism | Mapping notes |
| --- | --- | --- | --- |
| OBS-01 Authorization decision reconstruction | B | Approval records in thread items; execpolicy decisions (`execpolicy/src/decision.rs`) | Whether an independent reader can attribute actor/authority from persisted records. |
| OBS-02 Collector failure and publisher durability | B | `codex-rs/otel` OTLP metrics export; events | Same outage/restart/overload arms against the real export path. |
| OBS-03 Blind diagnosis of known faults | A | Same blind-reader protocol over rollout + logs + notifications | Unchanged. |
| OBS-04 Retention, export, and tamper boundaries | A | Rollout retention/maintenance (`rollout/src/maintenance.rs`); export surfaces; file ownership | Unchanged. |
| OBS-05 Diagnosis and operational burden | A | `codex doctor`; `codex debug` tooling | Native diagnosis path is directly available. |
| OBS-06 Open task trajectories and causal linkage | A | Rollout JSONL causal chain; ServerNotification stream linkage | Same model-identity/tool-linkage questions. |
| OBS-07 Practical trace access, export and defect diagnosis | A | `codex-rs/rollout-trace`; `codex debug` | Unchanged. |

## Class summary

| Class | Families | Reading |
| --- | ---: | --- |
| A direct map | 39 | Controller drives the equivalent native surface; original acceptance intent kept. |
| B equivalent rewrite | 17 | Capability exists under a different contract; scenarios rewritten, acceptance question preserved. |
| C probe first | 4 | REL-08 (Windows arms), PERF-07, COST-05, plus EXT-08's unsupported-hook subset. Verified nonapplicability requires a native probe and a pinned support contract; never a silent skip. |

All 60 families and 257 scenario slots are preserved. This mapping is the
preregistration input for the Codex matrix; the matrix remains the authoritative
frozen design and is generated next.
