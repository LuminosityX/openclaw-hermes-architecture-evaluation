# Current stable pilot evidence: OpenClaw 2026.10.7

The [campaign manifest](campaign.json) binds the current-release observations to OpenClaw `2026.10.7`, release commit `157d8c2bc3ea2fa183afdc11088e69690bf8e64e`, Node `24.22.1`, npm integrity and exact controller commits. Published installation identity and the dependency lock are retained. All execution ran on disposable GitHub-hosted Ubuntu machines; no new runtime or dependency cache was installed on the user's local machine.

Three exploratory studies each have two independent paired blocks with valid controls. ARC-01 and ARC-03 come from [run 40269017948](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40269017948); that job later failed a different study's MCP catalog parsing. The corrected ARC-02 alone comes from successful [run 40269524944](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/actions/runs/40269524944). The manifest selects studies explicitly rather than treating the first job as wholly successful or inflating sample counts across retries. Raw reports and per-run controller hashes remain unchanged.

| Study | Observation on this release | Limit |
| --- | --- | --- |
| ARC-01 | All 32 tasks completed, with one independent effect and matching native receipt per task. Cap 1 produced actual effect overlap 1; cap 4 produced overlap 4. Goodput was 1.85/1.71 tasks/s at cap 1 and 1.77/1.96 at cap 4. | No consistent throughput gain in this short-task, two-core profile. This does not establish a general scalability limit or identify preparation, catalog calls or CPU quota as the sole bottleneck. |
| ARC-03 | Both paired blocks showed agent-scoped SSH workspace reuse, session-scoped separation, and retained state when revisiting the writer session. | Workspace ownership on an owned loopback SSH server, not hostile-tenant OS isolation, Docker performance or a real remote-host benchmark. |
| ARC-02 | In both blocks the native plugin's controlled `exit(42)` ended its Gateway. The external MCP process exited while its Gateway remained alive and independent neighbor requests succeeded. Block-time neighbor latency was 1222/1185 ms for the plugin route and 928/959 ms for MCP. | Route and transport differ; baseline neighbor latency also varied. The samples do not establish a pure isolation-cost effect, population latency quantiles or fault rates. |

Native Tool Search remains at this release's default. The deterministic provider searches, describes and invokes the advertised catalog target; it does not disable discovery to emulate the old build. MCP metadata's external-content wrapper is preserved in native records while the fixture extracts only matching catalog data. Successful task responses still require a real receipt from the independent effect ledger.

## Setup attempts and resource conditions

Earlier attempts remain classified in the manifest. One aborted before resource diagnostics existed. A subsequent 1536 MiB attempt recorded cgroup `oom=1`, `oom_kill=2`, and `oom_group_kill=1`. It produced no completed study and is not a product-result pass or a proven minimum-memory requirement. The campaign then used an explicitly declared 3072 MiB hosted memory ceiling, zero swap, two-core CPU quota, 128 processes/threads and 64 MiB runtime tmpfs. The retained valid-study jobs had no OOM events; CPU quota throttling occurred.

Two other attempts exposed fixture compatibility issues: assuming direct tools despite the release's catalog defaults, then failing to parse MCP catalog JSON inside its external-content warning. These are harness failures. Their fixes were checked with focused tests; valid unrelated studies were reused rather than repeatedly executed just to obtain a green whole-suite run.

The hosted jobs removed their own temporary installation and npm cache after execution, and only compact artifacts were retrieved. The dependency lock was minified for transport; the retained lock restores npm's two-space JSON formatting and its SHA-256 matches the original hash recorded by the installation verifier. The campaign manifest maps each job to its lock. No runtime snapshot, image, raw database or private SSH key is retained.

These are current-release exploratory observations. They are not a hardware-matched comparison with the historical local `2026.9.2` bootstrap, not complete execution of all 60 families, and not evidence about real-model problem solving, broad privacy/security, full trace export or actual token charges. No aggregate architecture score or designer intent is inferred.
