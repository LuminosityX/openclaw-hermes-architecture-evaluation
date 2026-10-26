# Effect loss, tool scheduling and policy resolution protocol

These adapters use the frozen campaign runtime and prescribed independent unit counts. All providers are deterministic local fixtures; no model capability or actual provider cost is inferred. Fixtures, native output and independent receipts are uploaded on GitHub. The evaluator never modifies the OpenClaw runtime.

## REL-02: external effect and lost acknowledgement

Each unit runs both an unkeyed remote effect and a remote effect with a stable synthetic idempotency key. A native Streamable HTTP MCP call reaches one of three independently observed boundaries: loss before commit, commit followed by actual connection shutdown, or commit with a held response followed by actual Gateway process-group termination. The matching native request must not report successful completion without its result, and native automatic replay must not increase the independent effect count. Framework automatic retry and an explicitly initiated evaluator/operator retry are counted separately.

After the fault, one explicit operator retry is performed against the same effect identity. The synthetic remote service deduplicates only the keyed arm. An unkeyed retry after a committed effect is expected to produce a second effect and is reported as such, not incorrectly attributed to an automatic framework replay. No automatic reconciliation is claimed from the model's text. For process death, the evaluator restarts the same native state; at most 30 seconds of narrowly matched, independently undispatched admission rejections are polled before the transport control and retry.

## PERF-03: actual native tool scheduling

Four owned UTF-8 files are read through native MCP tools, each with a fixed 250 ms remote wait. Tool result bytes must contain each file's distinct marker, and independent read receipts must show each call exactly once. S01 supplies four independent calls in one model response; S02 emits the next dependent call only after its predecessor's actual result. S03/S04 hold the parallel-call hint and workload constant while changing one versus two configured MCP peers. Native connection generations, read start/end times, overlap, endpoint wall time and sampled resources are retained. A configured peer is not assumed to imply exactly one physical connection. Parallel execution is measured rather than invented as a mandatory performance guarantee.

## SEC-05: effective policy sources

An initial positive native control establishes the configured tool and independent effect ledger. S01 explicitly selects a configuration path and removes that file; it measures native startup/dispatch behavior and diagnostics without assuming an enterprise administrator-policy feature. S02 installs malformed owned policy input, runs native config validation and attempts native startup. S03 conflicts a global deny with agent allow and project guidance. S04 changes a previously exercised allow to a deny and restarts the native Gateway. For S03/S04, the actual denied tool is requested through the model/tool path while a separately allowed neighbor tool proves service health. Effective policy, validation output, real tool returns and independent effects are retained. A restart-based rule change does not establish hot revocation or approval-race behavior.

Calibration must cover the whole family and validate invocation/fixture conditions before formal repetitions start. Product acceptance failures remain observations; missing fault boundaries, unavailable positive controls or fixture errors block that family.
