# V7 measurement contract

## Unit of evidence

Every run records the exact product revision, entry point, effective configuration, state schema, plugin/tool identities, host topology, fixture revision, and environment ownership. The experimental unit is an independently initialized service, connection, state profile, or host as appropriate. Requests inside one shared instance are repeated observations, not additional independent instances.

Choose repetitions from a pilot variance estimate and the required decision precision before the comparison. Functional failures need independent reproduction and an exact trigger boundary; absence of a failure in a few repetitions is not a broad reliability guarantee. Predeclare equivalence margins, latency quantiles, timeout handling, and stopping rules. Preserve failed, rejected, cancelled, and incomplete runs in denominators.

## Architecture attribution

Record process and thread identities, ownership of task state, persistence boundaries, queue positions, tool start/finish times, external effect IDs, and resource membership. A programming language is a relevant architecture choice, but it is not itself a measured bottleneck. Distinguish event-loop work, interpreter CPU execution, native code that releases interpreter locks, worker placement, IO waits, and application-level locks.

A causal comparison keeps the task contract fixed and changes one mechanism where the product supports it. If a private runtime patch is necessary, label the result as a counterfactual and keep it out of baseline grades. If multiple coupled mechanisms change, report an association rather than claiming a single cause. Validate observer overhead and ensure instrumented controls retain the same product behavior.

## Outcome axes

Report correctness, automation, availability, authority, performance, resource cost, and integration/operation effort separately. Preserve incomplete and unavailable outcomes. A collector record missing from an export does not prove that the native task was lost; a client response does not prove that its state was committed. An approval verdict does not identify approval scope.

Use an independent effect and event ledger as the oracle. Keep native records separate from that ledger, and withhold the oracle from blind diagnosis tasks. Compare equivalent semantics and documented permissions, including allowed-operation positive controls. Unsupported contracts, adapter work, harness errors, and violations of advertised support require different result labels.

## Failure timing and combinations

Synchronize faults with observable semantic events, not arbitrary startup sleeps. Sweep before/after durable admission, authorization, dispatch, external commit, result persistence, and acknowledgment. First isolate each mechanism, then test selected combinations such as collector outage plus publisher restart, task restart plus lost effect acknowledgment, and revocation plus delegated work. Define the combinations and expected invariants before execution.

## Resource and storage ownership

No experiment is enabled by this design branch. Before implementation is executed, declare whole-run and per-case limits for time, memory, disk blocks, inodes, processes, and connections. The disk budget must include shared application installations, package downloads/caches, writable fault-test generations, temporary output, and retained evidence.

Use one verified immutable application installation per pinned product/version where compatible with the test. Clone writable dependencies only for cases that require mutation. Record all owned paths and processes in a run manifest, prohibit deletion outside those roots, and preserve required evidence before cleanup. Measure open-but-deleted files and residual processes when accounting for reclaimed storage. Do not reuse shared personal caches as untracked experiment state.

## Execution and reporting gates

Each family starts as planned. It may advance only through fixture validation, adapter matching, execution, independent evidence verification, and review. CI validates the design and archived source; it is not product execution evidence. A fixture may not award a pass because a configuration field exists, a process starts, HTTP returns success, or an archive imports without a semantic continuation check.

Deterministic local fixtures come first. Only questions requiring actual provider usage or model behavior move to a separately budgeted real-model phase. No historical authorization string in a V6 controller supplies a current budget. No numeric score, statistical effect, or product conclusion is fabricated for a proposed test.
