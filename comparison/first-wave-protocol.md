# First-wave shared protocols — calibration in progress

These protocols use noninteractive entry points, an independent synthetic model endpoint, and operating-system observation. Codex is not run: its entry point has been checked through local help and source, not runtime calibration. DSH 0.2.2-alpha.2 and OpenClaw 2026.10.7 passed three hosted session-reconstruction calibration units. **Do not claim all three products can execute a scenario until all three adapters have been calibrated.** Equivalent external observations do not imply equivalent internal mechanisms.

Each independent unit uses a new isolated home, working directory, synthetic credentials, and local model service, with no real account. Record exact commands, binary versions, package integrity, configuration, process tree, and event times. The service returns fixed synthetic text and records requests and disconnects. Codex uses `codex exec --json`, `codex exec resume`, and the Responses protocol; DSH uses headless `--json` and `--session-id`; OpenClaw uses `agent --local` with an explicit session, plus a separate Gateway deployment for platform scenarios. The same fixture implements the products' different wire protocols with equivalent behavior. The controller starts, stops, and observes; it does not implement product retries or recovery.

## P01 — task ownership after an entry point exits

Submit the same task and hold the model response after the service confirms receipt. Terminate the entry process; observe the model connection, product processes, and task for 10 seconds, then inspect or resume through the native entry. Run OpenClaw Gateway and embedded configurations separately; use DSH headless and Codex exec for their respective entries. Record process IDs and ancestry, connection state, exits, recovery requests, and outcomes; mark unavailable observations unknown. Use three fresh units.

**Architecture question:** Does execution live in the caller or a separate service, and who owns surviving work and recovery after a disconnect? This is not a general crash-recovery or exactly-once guarantee. The external controller must verify that the fault reached the intended process.

## P02 / H05 — reconstruct a session after normal exit

Send `SESSION_MARKER_<unit>`; the fixture returns `ACK_<unit>`. After normal process exit, use native resume or the same session ID to send `CONTINUE_<unit>`. Independently verify that the second model request contains the earlier user marker, assistant acknowledgment, and new input. Record session identity, exit codes, persistence location, and recovery errors. Compare semantic content rather than a shared event schema. Use three fresh state directories per product. Missing first success or an unreached second request invalidates the unit; it is not a recovery failure.

**Architecture question:** Which state crosses a process boundary, and how is conversation context rebuilt? This does not establish recovery of in-flight tools, workspace changes, or external side effects.

## P03 — execution footprint and lifecycle

On the same host and synthetic service, record cold start to first request, sampled RSS across the product process tree, and processes remaining after exit. For Gateway-backed OpenClaw, report service startup and idle cost separately from marginal client-task cost; record other external components separately. Exclude the fixture. Use six fresh units per deployment and freeze the sampling interval, timeout, and service delay. Do not mix cache conditions. Summed RSS is not exclusive physical memory.

**Architecture question:** What are the lifecycle and resource tradeoffs of a shared service versus a per-invocation process? These measurements do not establish task throughput or a universal ranking.

## H07 — model request failure and retry

For a single turn, return HTTP 503 once, then a fixed acknowledgment in the appropriate protocol; also run a no-fault positive control. Independently record request count and intervals, user-message duplication, final state, and elapsed time. The controller never resends on the product's behalf. Use three fresh units.

**Architecture question:** Where does native retry happen, and what attempts and delay does it introduce? This does not establish safety after a streamed response or tool side effect. Codex's Responses error format and retry configuration require source review; runtime behavior remains unverified.

## Validity and completion

Keep calibration separate from formal results. A valid unit needs a passing positive control, verified fault reachability, an identifiable native entry, and independently retained evidence. An unmet precondition is untested or blocked, not a product failure. Keep valid failed observations. Report each system first, then aligned conditions and remaining confounders. Mark a new work item complete only after the prescribed independent formal units and evidence review. Compaction, tool scheduling, approvals, and large outputs remain candidates until common tool and control surfaces are calibrated across all three systems.
