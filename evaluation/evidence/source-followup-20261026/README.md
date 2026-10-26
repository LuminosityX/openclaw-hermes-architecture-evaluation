# Source review and discriminating experiments

The work unit here is **observation → versioned implementation → falsifiable explanation → intervention → six-dimensional interpretation**. It is not the number of passing groups. The three earlier pilots supplied observations; this dossier follows them into the exact `2026.10.7` source, corrects an evaluator-induced explanation, and tests alternative mechanisms.

The overall logic visible in this evaluated embedded-runtime path is a shared Gateway that owns admission, session/state coordination and authority, with pluggable execution edges. Code plugins extend that process deeply; MCP moves a narrower contract across a process boundary; SSH delegates execution to a configured remote principal. Deferred tool catalogs bound model-facing schema growth without bypassing the execution pipeline. These boundaries solve different problems and cannot be substituted for one another. Other agent harnesses and backends require their own source/evidence chain.

Start with [reviewed findings](findings.json), [paired comparisons](comparisons.json) and the [campaign/source-job manifest](campaign.json). The [pre-execution source anchors](source-map.json) bind 15 modules to full SHA-256 hashes and immutable source lines. The [post-run source inspection](posthoc-source-map.json) explicitly separates additional lookups prompted by CPU samples, callback PIDs and error logs from the original predictions. No product source file was patched for these experiments.

## 1. Four model turns were our strategy, not the framework's minimum

The initial provider always searched, described, invoked, then finalized. But [`findEntry`](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/agents/tool-search-runtime.ts#L81-L109) accepts an exact ID or unambiguous name, and [`call`](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/agents/tool-search-runtime.ts#L313-L320) does not require a prior search/describe event. Treating all four requests as unavoidable architecture overhead was therefore unjustified.

SRC-01 preserved the native default and changed only the controlled provider's discovery strategy. Each eight-task batch used 32 requests under full discovery and 16 under known-name invocation, in both blocks. Correct effects and native receipts remained intact. This verifies what the API permits, not a real model's ability to choose correct names and arguments without discovery.

The next contrast held known-argument operation semantics fixed and used the public `tools.toolSearch: false` setting for full schemas:

| 64 eligible tools, eight tasks | Native deferred catalog | Direct schemas |
| --- | --- | --- |
| Provider requests | 16 | 16 |
| Aggregate tool-schema bytes | 38,160 | 838,368 |
| Aggregate full request-body bytes | 292,400 | 1,001,200 |
| Goodput, blocks 0 / 1 | 1.408 / 1.823 tasks/s | 1.636 / 1.571 tasks/s |
| Batch user CPU, blocks 0 / 1 | 8.69 / 6.39 s | 7.19 / 7.51 s |

The catalog reduced full wire volume about **70.8%** and schema volume about **95.4%** in these deterministic batches. Its schema-control surface remained bounded as the eligible catalog grew, although the directory and full body still grew. This is concrete support for the source's [per-call context tax / extensibility objective](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/VISION.md#L71-L94).

CPU and goodput changed direction between blocks. We cannot conclude that the context benefit necessarily sacrifices performance, or that two small blocks establish equivalence. Request/schema/body bytes are not actual billed tokens or dollars. Both modes also rejected a registered-but-excluded tool without producing its effect; a known name was not a tested permission bypass. The [authorized-tool assembly](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/agents/agent-tools.ts#L531-L567) and execution wrappers remain part of the path.

## 2. More admission slots help overlap waiting, not create four JS threads

[`server-lanes.ts`](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/gateway/server-lanes.ts#L26-L35) resolves the configured main-lane budget. The embedded runner places global admission inside [session admission](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/agents/embedded-agent-runner/run-orchestrator.ts#L717-L733). The [queue](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/process/command-queue.ts#L343-L389) counts active asynchronous tasks and releases a slot when its task settles. The concurrency knob does not by itself create a JavaScript thread per run.

SRC-02 held known-name invocation fixed and crossed cap 1/4 with actual independent waits of 150/1500 ms. All 64 measured tasks completed with exactly one effect and a matching native receipt.

| Effect wait | Cap 1 goodput, blocks 0 / 1 | Cap 4 goodput, blocks 0 / 1 | Paired gain |
| --- | --- | --- | --- |
| 150 ms | 1.598 / 1.541 | 1.854 / 2.272 | 1.16× / 1.47× |
| 1500 ms | 0.502 / 0.499 | 1.265 / 1.256 | about 2.52× in both blocks |

The controlled wait change made concurrency much more useful. All callback PIDs matched the inspected Gateway owner and reported its main thread. For long waits, the main-thread profile's idle sample fraction was about 78% at cap 1 and 46–48% at cap 4. These are **main-thread sample fractions**, not whole-process CPU utilization: SQLite and other workers can run while that thread is idle.

This supports a workload-dependent asynchronous-overlap explanation. It does not prove that all short-task residual cost comes from one lock, path check, redactor or the programming language. The source contains real per-session/state coordination constraints, but these tests used independent sessions and did not ablate ordering. A stronger causal claim about the cost of that ordering would require another controlled test.

## 3. Logical plugin scope is not process or filesystem isolation

The [tool registrar](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/plugins/registry-registrars-tools-hooks.ts#L220-L267) retains executable factories. [`PluginInstance.invoke`](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/plugins/plugin-instance.ts#L361-L415) runs the callback under invocation/lifecycle ownership; these scopes are not OS processes. The [tool adapter](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/agents/agent-tool-definition-adapter.ts#L238-L265) converts ordinary execution errors into tool-error results.

SRC-03 tested the distinction rather than generalizing every plugin fault:

- All four ordinary-throw probes retained the original Gateway owner PID and served an independent request afterward.
- Native plugin callbacks matched the Gateway PID and reported `isMainThread: true`; explicit process termination interrupted the target and independent service requests. One immediate poll captured exit 42; another caught a transitional live process while its service was already unavailable. The raw field is retained, not silently rewritten. Future code now waits passively for a bounded natural-settlement window before interpreting process state.
- External MCP callbacks had different PIDs, and their process exits left independent Gateway requests working. They still ran under UID 0 and read the same explicitly accessible synthetic file as the code plugin. A different PID was not a different OS authority boundary.

There is also a lifecycle confound in a simple latency comparison: each probe used a fresh session. The source [acquires the static MCP runtime under `params.sessionId`](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/agents/agent-bundle-mcp-manager.ts#L205-L221); the observed MCP callback PIDs differed across these requests. Transport, session runtime acquisition and callback interfaces differ, so their latency delta is not a pure IPC tax.

The [documented design](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/VISION.md#L86-L94) chooses code plugins for deeper hooks/providers/channels/tools and narrower bundle-style surfaces when sufficient. Source and runtime identity explain the shared termination/authority domain. They do **not** establish that the integration benefit outweighs its cost, that every exception kills the service, or that external processes safely contain hostile code.

## 4. A workspace key does not assign a new SSH principal

[`resolveSandboxScopeKey`](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/agents/sandbox/shared.ts#L55-L88) selects an agent/session/workspace-qualified key. The remote backend [maps it to directories](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/agents/sandbox/remote-shell-backend.ts#L436-L447). SSH configuration independently selects [host, user and key](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/agents/sandbox/ssh.ts#L101-L128); shell execution [changes directory before executing the command](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/agents/sandbox/remote-shell-command.ts#L171-L195).

SRC-04 preserved the relative-path separation result, then performed an explicit read of the owned sibling canary. All four reads returned `readable: true` under the same root SSH identity. Session scope prevented accidental relative-state reuse here; it did not turn this SSH deployment into an OS filesystem jail.

This is a responsibility/configuration boundary, not a claim that OpenClaw universally sacrifices security for convenience. A different SSH principal or container backend changes the deployment. Native file-tool path checks and arbitrary shell execution also need separate contracts; this test exercised `exec` on the SSH backend, not every file-tool path.

## 5. Error preview detail is intentionally limited for privacy

The throw records show the synthetic `token` argument replaced by `***`. Source inspection explains the exact path: [parameter preview redaction](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/agents/agent-tool-definition-adapter.ts#L104-L107) calls tool-payload redaction, which [forces tools-mode defaults](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/logging/redact.ts#L833-L845) rather than inheriting an arbitrary off mode. The [JSON-field pattern](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/logging/redact-patterns.ts#L42-L43) includes credential-shaped keys such as `token`.

This is a concrete privacy-versus-raw-preview choice: the operator log does not reproduce that field exactly, even when its value is our benign correlation marker. It does not establish global privacy effectiveness or a lack of detail in every authorized trace/export. Privileged SQLite inspection in this evaluator is likewise not proof of an easy public debugging interface. Keep non-sensitive correlation IDs separate from secret fields rather than weakening credential redaction to debug a task.

## Joint interpretation across the six dimensions

| Dimension | What source plus these observations support | What remains a cost, boundary or unknown |
| --- | --- | --- |
| Reliability | Session/global admission and ordinary tool-error conversion have explicit owners; controlled task effects and native receipts remained consistent. | A trusted code plugin can terminate the shared service. Restart durability, duplicate replay and cross-session mutation correctness are not established here. |
| Security/privacy | A known catalog ID/name did not invoke an excluded registered tool in 16 controls; tool-error previews deliberately redact credential-shaped fields. | Code trust, tool delegation policy, process boundaries and SSH principals are separate layers. Shared UID/root SSH is not hostile-tenant isolation. |
| Performance | Asynchronous admission realizes much more benefit with longer independent waits; callback execution was on the Gateway main thread. | More admitted runs do not create JS threads. Residual CPU/state/worker costs are not uniquely attributed, and a language-level ranking would be unjustified. |
| Resources/cost | Deferred schemas materially reduce wire/context footprint at 64 tools with equal request counts under known-name dispatch. Batch CPU is separated from startup. | CPU/goodput costs were not consistently worse or better. Bytes and synthetic usage do not establish actual tokens or money. |
| Extensibility | Code plugins retain callable factories and lifecycle access; narrower external routes use different ownership and transport contracts. | Shared fault/authority scope accompanies deep code extension. Different sessions also acquire different MCP runtimes, confounding a simple IPC-cost story. |
| Observability | PID/thread identity, independent effect truth, native receipts, sampled stacks and exact source anchors together explain more than a final response. | Redacted previews intentionally lose raw detail. Privileged DB inspection is not proof of an easy, complete public trajectory/export or successful blind diagnosis. |

## What remains unresolved

The main-thread stacks include alias canonicalization, state-owner checks, worker admission and redaction. Returning to source reveals why they exist: aliases must converge on one resource identity; ordinary state access must respect current ownership and maintenance; tool errors must not expose credentials. The [owner reader](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/src/infra/gateway-state-owner.ts#L637-L685) already has expiry/heartbeat/current-owner-conditioned caching. Seeing `realpath` in a sparse sample does not prove absence of caching or make it the dominant bottleneck.

The next source-bound hypothesis is to test stable-path/cache behavior against owned alias/owner-lock replacement while preserving correctness. A private guard bypass, if ever used, must be labeled a counterfactual and paired with the failure it could admit; faster timings alone are not evidence of a valid improvement. This remains open, not a concluded reliability/performance tradeoff.

Real-model task quality, billed token cost, broad privacy/network attacks, full recovery/durability, public trace/export usability and general fault probabilities remain unmeasured. The current result is a source-backed explanation of these observations and sharper next questions, not a six-axis product grade.

## Evidence and storage

All four selected source-followup jobs completed. There are 24 fresh Gateway arms across the four investigations, with paired order reversal, two-core/3 GiB hosted budgets, bounded 64 MiB runtime state and no paid model calls. A previous aggregate run exceeded its 600-second campaign limit; that is retained in the manifest as an evaluator budget failure, not a product failure. Experiments were split into independent hosted lanes. Completed-arm checkpoints now survive outer failures, and refusal probes request an excluded operation once instead of potentially driving a repair loop.

Only compact observations, approximate hot-stack summaries, source excerpts/hashes and installation identities are retained. The unchanged dependency lock is referenced from the existing current-release evidence rather than copied. Raw CPU profiles, runtime installations, databases, private SSH keys and downloaded transport duplicates are discarded. Main-thread profiling is diagnostic instrumentation; sample counts and bundle-region hints are not exact per-function CPU accounting or an independently verified source-map translation.
