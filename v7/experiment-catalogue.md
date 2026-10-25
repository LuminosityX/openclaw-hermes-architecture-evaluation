# V7 experiment catalogue

Status: proposed experiment families, not executed tests. The [machine-readable matrix](design/evaluation-matrix.json) is authoritative for this catalogue. Each family requires a matched fixture and product adapter before it becomes executable.

## D01 — Reliability and recoverability

V6 already tests restart and side effects. Its own evidence review leaves the complete intervention-time contract unresolved; fixed trigger points also need systematic coverage of persistence and acknowledgment boundaries.

### D01-01 — Admission and persistence boundaries

Architecture mechanism: The task-admission acknowledgment and durable task record can be committed at different times.

Controlled change: Inject termination at instrumented boundaries; distinguish a task acknowledged as durable from a merely received request.

Scenarios: before durable append; after durable append but before client acknowledgment; after acknowledgment but before worker dispatch.

Pass/failure evidence: Compare acknowledged task IDs with durable records and completed work after restart; report the unacknowledged ambiguity window separately.

Measurements: lost acknowledged tasks, duplicate dispatches, recovery latency, durability window.

### D01-02 — External effects and lost acknowledgments

Architecture mechanism: A remote side effect and the agent checkpoint do not share a transaction.

Controlled change: Use a local side-effect server with an independent ledger; drop the response after commit, with and without an idempotency key.

Scenarios: effect not committed; effect committed and response lost; process dies before recording the tool result.

Pass/failure evidence: The ledger must show the exact effect count; separate correct reconciliation, safe uncertainty, incorrect replay, and falsely reported completion.

Measurements: duplicate effects, unresolved effects, automatic reconciliation rate, operator actions.

### D01-03 — Delegated work and stale owners

Architecture mechanism: Parent-child state, leases, and result publication may have different owners.

Controlled change: Terminate or partition the parent and child independently; allow a stale worker to publish after reassignment.

Scenarios: parent restart while child runs; child restart after effect commit; lease expiry and delayed stale result.

Pass/failure evidence: Track ownership epochs, child identities, accepted results, and effect IDs; a stale result must not silently overwrite the current result.

Measurements: orphaned work, stale commits, duplicate effects, time to converge.

### D01-04 — Recovery automation and service availability

Architecture mechanism: A plugin, worker, and request service can share or separate physical execution lifetimes.

Controlled change: Terminate only the identified plugin host, execution worker, or gateway; keep an unrelated session active.

Scenarios: plugin exits; worker exits; gateway restarts; manual confirmation is required.

Pass/failure evidence: Record which sessions stop and which resume automatically; availability, recovery correctness, and required human work remain separate outcomes.

Measurements: affected sessions, service downtime, automatic resume rate, manual steps and active operator time.

## D02 — Security and isolation

V6 includes real boundary probes and permission controls. The next design must enumerate every execution surface and test combinations of capabilities, delegation, and concurrent tenants rather than extrapolating from one sandbox path.

### D02-01 — Execution-surface authority

Architecture mechanism: Shell tools, file tools, MCP servers, in-process plugins, and separate plugin processes can receive different host capabilities.

Controlled change: Apply the same allowed and denied filesystem, network, process, and environment probes through each supported surface.

Scenarios: shell tool; native file tool; MCP server; in-process plugin; separate plugin process.

Pass/failure evidence: Use OS-visible effects and local network receipts; a model refusal or separate process ID alone does not establish isolation.

Measurements: denied effects that succeeded, allowed positive controls, effective UID and capabilities, reachable host resources.

### D02-02 — Credential propagation and revocation

Architecture mechanism: Credentials can be copied into child environments or cached connections beyond their intended lifetime.

Controlled change: Grant one synthetic capability, delegate work, revoke it, and retry through the original and delegated paths.

Scenarios: fresh process; reused connection; child task; plugin restart.

Pass/failure evidence: Synthetic credential use is accepted only within the declared grant and revocation semantics; trace propagation without placing real secrets in the fixture.

Measurements: unexpected credential reach, revocation lag, post-revocation effects, unnecessary grant breadth.

### D02-03 — Isolation setup and path races

Architecture mechanism: Sandbox setup failures and filesystem aliases can bypass an intended resource boundary.

Controlled change: Force a declared isolation backend to fail and race symlink or rename changes against file access.

Scenarios: backend unavailable; bind or permission setup fails; symlink target changes; allowed file accessed as a positive control.

Pass/failure evidence: The action must either remain within the verified boundary or fail visibly; backend errors must not silently select an unrestricted path.

Measurements: fail-open dispatches, alias escapes, clear failures, cleanup residuals.

### D02-04 — Cross-session authority separation

Architecture mechanism: Shared caches, pooled workers, and reused plugin state can carry data between sessions.

Controlled change: Run two synthetic tenants concurrently, restart pooled components, and attempt cross-session reads or credential reuse.

Scenarios: sequential worker reuse; concurrent requests; cached tool result; restarted plugin host.

Pass/failure evidence: Each tenant can access only its own explicitly granted artifacts; shared public cache entries must be distinguished from tenant data.

Measurements: cross-session disclosures, state-key collisions, inherited environment data, authorized sharing success.

## D03 — Architectural control

V6 tests policy loading, approval, cancellation, and delegation. More evidence is needed about policy changes between authorization and dispatch, concurrent budgets, and consistency across all execution entry points.

### D03-01 — Policy resolution across entry points

Architecture mechanism: Policy sources, precedence, and enforcement locations can differ between CLI, gateway, child tasks, and resumed work.

Controlled change: Identify each product's actual mandatory and optional policy files, then vary one layer while sending the same operation through each supported entry point.

Scenarios: missing mandatory policy; malformed policy; conflicting project rule; restart with a changed rule.

Pass/failure evidence: Compare effective policy provenance with the actual operation; do not call every missing configuration file an administrator-policy failure.

Measurements: enforcement disagreement, silent policy fallback, policy version in decisions, explicit diagnostic quality.

### D03-02 — Revocation between approval and dispatch

Architecture mechanism: Checking permission once does not necessarily bind authorization to the final operation.

Controlled change: Pause after approval, change the policy or resource target, and then permit dispatch.

Scenarios: single-use approval; session approval; delegated approval; queued operation.

Pass/failure evidence: The effect must follow the documented revocation and target-binding contract; record check time, dispatch time, actor, and policy version.

Measurements: stale authorizations, approval reuse, revocation lag, policy checks per dispatch.

### D03-03 — Cancellation across descendants

Architecture mechanism: Cancellation can stop the client while queued work or child processes continue.

Controlled change: Cancel at each execution boundary and inspect all descendants and externally observable effects.

Scenarios: queued request; running synchronous tool; background child; checkpointed resumable work.

Pass/failure evidence: Classify intentionally durable work separately; non-durable cancelled work must not continue producing forbidden effects.

Measurements: post-cancel effects, surviving descendants, queue removal latency, resource reclamation latency.

### D03-04 — Concurrent budget enforcement

Architecture mechanism: A budget maintained per worker can overshoot a task-wide limit when work is delegated or concurrent.

Controlled change: Use a local metered fixture and issue concurrent requests that compete for the same task budget.

Scenarios: two sibling tasks; retry consumes remaining budget; tool and model limits interact; restart preserves consumed budget.

Pass/failure evidence: An independent usage ledger determines the total; distinguish admission reservations from actual usage and explicit overshoot bounds.

Measurements: global budget overshoot, double reservations, unaccounted retries, incorrectly rejected allowed work.

## D04 — Performance and responsiveness

V6 measures matched task latency, gateway latency, and MCP critical paths. Aggregate latency still cannot identify whether context construction, event-loop work, Python CPU work, connection locks, or queueing caused the difference.

### D04-01 — Request preparation on the service path

Architecture mechanism: Tool-schema construction and conversation preparation can execute on the request-serving thread or on an execution worker.

Controlled change: Increase schema count and history size independently while issuing unrelated short requests.

Scenarios: small versus large tool catalogue; short versus long history; cold versus warm component cache.

Pass/failure evidence: Attribute preparation spans to concrete process and thread identities; an unrelated request provides a direct responsiveness control.

Measurements: preparation CPU time, event-loop lag, queue wait, unrelated-request first-text p95.

### D04-02 — CPU work versus asynchronous waiting

Architecture mechanism: Node.js event-loop scheduling, Python interpreter execution, and worker placement affect different kinds of work differently.

Controlled change: Use matched CPU-bound preparation and IO-wait fixtures; where supported, change worker placement without changing the fixture result.

Scenarios: CPU-bound preparation; IO-bound preparation; one session; multiple independent sessions.

Pass/failure evidence: Record wall time, per-thread CPU, runnable time, and service progress; language choice alone is not a causal explanation.

Measurements: CPU attribution, runnable delay, throughput, short-request tail latency.

### D04-03 — Tool scheduling and connection locks

Architecture mechanism: Dependency ordering and transport-level serialization can constrain otherwise independent tools.

Controlled change: Run the same dependency graph over one connection and multiple independent connections; include ordered mutating operations.

Scenarios: independent reads; dependency chain; single connection; separate connections.

Pass/failure evidence: Compare tool start and finish events with the dependency graph; speedups that violate required ordering are failures.

Measurements: critical-path length, actual overlap, lock wait, ordering violations.

### D04-04 — Fairness during a slow task

Architecture mechanism: Worker execution can be separate while admission queues or shared state still delay new requests.

Controlled change: Mix long and short requests under a fixed arrival schedule; vary only queue or worker configuration when officially configurable.

Scenarios: one slow tool; large preparation task; burst of short requests; cancellation of the slow task.

Pass/failure evidence: Report acceptance, queueing, first text, and completion independently for each request class.

Measurements: short-request p95 and p99, starvation duration, admission latency, goodput.

## D05 — Resource and cost efficiency

V6 retains full-process resource checks and actual API accounting, but its final resource/cost dimension remains ungraded. The architecture review must separate resident baseline, marginal concurrency cost, reuse amortization, and disk amplification.

### D05-01 — Resident baseline and marginal session memory

Architecture mechanism: Shared runtimes and separate execution processes trade baseline memory against per-session memory and isolation.

Controlled change: Measure an idle service and increasing active sessions with identical tool and context payloads.

Scenarios: idle service; one session; four sessions; sixteen sessions; post-completion idle.

Pass/failure evidence: Use complete process and container membership; report PSS and cgroup accounting separately instead of treating RSS sums as physical memory.

Measurements: resident baseline, memory slope per session, peak cgroup memory, retained memory after completion.

### D05-02 — Initialization and component reuse

Architecture mechanism: Repeated runtime initialization and component loading can dominate short tasks.

Controlled change: Compare fresh execution with reuse of the same supported components, separating filesystem cache state from application reuse.

Scenarios: cold process and cold cache; cold process and warm cache; warm process; repeated plugin loading.

Pass/failure evidence: The task and component versions remain identical; record exactly which initialization steps are avoided.

Measurements: startup CPU, initialization wall time, bytes loaded, memory retained for reuse.

### D05-03 — Learning and context cost amortization

Architecture mechanism: Learning, retrieval, context construction, retries, and stale assets change cost over a sequence of tasks.

Controlled change: Use equal-quality task sequences with and without native reusable assets; introduce a rule change after several reuse horizons.

Scenarios: one later task; five later tasks; twenty later tasks; rule change with stale assets.

Pass/failure evidence: Use real provider usage only in a separately budgeted phase, including learning, auxiliary calls, failures, and retries; synthetic usage is never a price measurement.

Measurements: cost per accepted delivery, reuse break-even point, context tokens, stale-rule failures.

### D05-04 — Disk and inode amplification

Architecture mechanism: Copying whole dependency trees per case multiplies storage without adding independent experimental evidence.

Controlled change: Compare a shared immutable installation with the documented writable-copy path required for installation or fault tests.

Scenarios: one run; many short runs; interrupted setup; cleanup after evidence retention.

Pass/failure evidence: Count allocated blocks, apparent bytes, inodes, caches, and open-but-deleted files against an explicit run ownership manifest.

Measurements: allocated bytes per run, dependency duplication factor, inode growth, residual bytes after cleanup.

## D06 — Scalability

V6 tests concurrency up to sixteen and two isolated nodes on one host. Those results do not establish behavior under overload, independent-host expansion, state contention, or long-duration resource growth.

### D06-01 — Admission and overload behavior

Architecture mechanism: Queue capacity and admission control determine whether load becomes bounded rejection or unbounded waiting.

Controlled change: Use an open-loop arrival schedule below, near, and above measured sustainable capacity.

Scenarios: steady load; burst load; slow external service; overload recovery.

Pass/failure evidence: Count every offered request, including rejected, cancelled, timed-out, and incorrect work; do not hide overload through client-side waiting.

Measurements: offered and admitted rate, correct goodput, queue depth, tail latency, recovery time.

### D06-02 — State contention under parallel sessions

Architecture mechanism: Shared session stores and connection locks can limit concurrency independently of available workers.

Controlled change: Compare independent sessions with concurrent operations against the same declared shared state.

Scenarios: independent sessions; same-session updates; long state transaction; delayed result commit.

Pass/failure evidence: Check for lost updates and transaction violations while tracing lock or commit waits.

Measurements: conflicts, lost updates, state-lock wait, throughput scaling.

### D06-03 — Actual multi-host execution

Architecture mechanism: A second HTTP entry point or remote shell does not prove that the complete agent execution unit can move to another host.

Controlled change: Use independent hosts with controlled placement, then remove one host while work is active.

Scenarios: one host; two independent hosts; worker-host loss; network partition.

Pass/failure evidence: Verify placement of the model loop, state owner, tools, and result commit; mark unavailable hosts as untested rather than simulating a claim.

Measurements: placement evidence, additional usable capacity, orphaned work, cross-host recovery.

### D06-04 — Sustained load and recycling

Architecture mechanism: Resident workers, state caches, queues, and connections may grow across many completed tasks.

Controlled change: Run bounded-duration deterministic load with a fixed active concurrency, then drain and optionally recycle supported workers.

Scenarios: steady workload; repeated session creation; repeated connection errors; drain to idle.

Pass/failure evidence: Predeclare duration, disk limits, and leak-slope criteria; report interrupted runs as censored rather than successful.

Measurements: memory growth slope, descriptor and connection growth, queue growth, post-drain baseline.

## D07 — Modifiability and extensibility

V6 exercises public extension routes and lifecycle operations. The next step must distinguish replacing a tool, context preparation, a provider adapter, and the full agent harness, and must test state obligations during replacement.

### D07-01 — Extension replacement during active work

Architecture mechanism: Registration and disable operations can affect new dispatches differently from already running calls.

Controlled change: Install, update, disable, and uninstall the same extension while one invocation is paused.

Scenarios: new call after disable; in-flight call during update; restart after uninstall; failed replacement.

Pass/failure evidence: Verify documented lifecycle semantics and state ownership; record how many core changes or private patches are required.

Measurements: stale registrations, residual effects, public-interface coverage, required core modification scope.

### D07-02 — Full harness replacement versus provider routing

Architecture mechanism: Delegating to a model provider or external tool may leave the original agent loop and state ownership intact.

Controlled change: Integrate the same reference external harness through each documented route and trace ownership end to end.

Scenarios: tool delegation; provider plugin; public harness interface where present; resume after external harness failure.

Pass/failure evidence: Identify the owner of planning, tool selection, checkpoints, cancellation, and result commits; do not label all routes equivalent harness support.

Measurements: ownership handoffs, missing lifecycle callbacks, recovery obligations, adapter and core change scope.

### D07-03 — Extension API and version skew

Architecture mechanism: An interface may work for one exact version while exposing private product objects or undocumented assumptions.

Controlled change: Run the same extension against declared compatible versions, including additive schema changes and missing optional capabilities.

Scenarios: old extension on new supported version; optional field added; capability absent; extension startup fails.

Pass/failure evidence: Judge against the actual compatibility promise and explicit rejection behavior, not arbitrary cross-version expectations.

Measurements: supported combinations, silent semantic drift, compatibility diagnostics, maintenance surface.

### D07-04 — Context and persistence contracts

Architecture mechanism: Replacing context preparation can change token allocation, memory retrieval, or persistent state behavior.

Controlled change: Swap a reference context component while preserving task state and a fixed model-visible contract.

Scenarios: normal task; context limit reached; checkpoint and restart; component disabled.

Pass/failure evidence: Assert which state the extension may write and which invariants remain core-owned; no hidden answer injection is permitted.

Measurements: semantic regressions, state coupling, public hooks required, rollback cleanliness.

## D08 — Portability

V6 validates changed Linux paths and dependency reconstruction, but its own evidence records native cross-OS execution as unavailable. File transfer, identity continuity, credential rebind, and actual execution must be separated.

### D08-01 — State identity under relocation

Architecture mechanism: Absolute directories and derived identifiers can bind otherwise portable state to one deployment.

Controlled change: Change home, state directory, workspace path, and UID independently before a combined relocation.

Scenarios: state path only; workspace path only; UID only; combined relocation.

Pass/failure evidence: Inventory content, session identity, scheduled work, extension state, and continuation behavior after native startup.

Measurements: identity continuity, missing or duplicated tasks, manual path repair, accepted continuation.

### D08-02 — Dependency reconstruction without host leakage

Architecture mechanism: A restored application can accidentally depend on binaries, caches, or configuration from the original host.

Controlled change: Reconstruct exact pinned dependencies in a clean environment with the source host paths unavailable.

Scenarios: empty cache; preverified local package cache; missing dependency; dependency checksum mismatch.

Pass/failure evidence: Record all runtime resolutions and reject undeclared host dependencies; package setup failure is an environment outcome until attributed.

Measurements: undeclared dependencies, reconstruction steps, downloaded and installed bytes, rebuild reproducibility.

### D08-03 — Native cross-OS semantics

Architecture mechanism: Filesystem naming, process control, paths, and native state formats can differ by operating system.

Controlled change: Use real Linux and Windows executors, and any additional OS only when available, with the same semantic fixture.

Scenarios: Unicode and path behavior; process cancellation; state import; native session continuation.

Pass/failure evidence: Require actual target execution and independent artifact checks; syntax checks and upstream CI are not migration results.

Measurements: semantic preservation, unsupported combinations, native execution evidence, repair steps.

### D08-04 — Credential and endpoint rebind

Architecture mechanism: Portable state must not require transplanting machine-bound credentials or using an obsolete service identity.

Controlled change: Move synthetic state to a new endpoint and credential authority without copying the original secret material.

Scenarios: endpoint changes; credential rotates; old endpoint unavailable; revoked old credential.

Pass/failure evidence: Resume only within the new deployment's grants; identify state that intentionally cannot migrate.

Measurements: stale endpoint use, credential coupling, rebind actions, task continuation.

## D09 — Observability and auditability

V6 already distinguishes native records from external truth and contains matched short collector-outage controls. Its own review leaves complete retention/export contracts unresolved; exact approval scope and crash persistence require explicit tests.

### D09-01 — Authorization decision reconstruction

Architecture mechanism: An allowed verdict can omit whether the approval was single-use, session-scoped, persistent, inherited, or policy-derived.

Controlled change: Exercise each declared approval mode and reconstruct actor, target, policy version, and scope using product records alone.

Scenarios: single-use grant; session grant; persistent grant; revoked inherited grant.

Pass/failure evidence: A reviewer must identify the actual authorization choice, not merely approved versus denied; truth is held separately.

Measurements: scope reconstruction accuracy, actor and task linkage, missing decision fields, ambiguous records.

### D09-02 — Collector failure and publisher durability

Architecture mechanism: A retry queue may be memory-only or durable, and a local transcript may survive when remote export does not.

Controlled change: Fail the collector at a matched event boundary, then restart the publisher or exhaust its declared buffer.

Scenarios: brief outage; long outage; publisher restart; buffer capacity reached.

Pass/failure evidence: Compare native local records and exported events independently against event IDs; distinguish duplicate delivery from missing events.

Measurements: lost events, duplicate deliveries, durable replay after restart, overflow signaling.

### D09-03 — Blind diagnosis of known faults

Architecture mechanism: Many log lines do not guarantee that an operator can reconstruct causal order or distinguish retries from duplicate effects.

Controlled change: Give a reviewer only product records for predeclared injected faults; withhold the independent truth ledger until scoring.

Scenarios: retry after lost acknowledgment; parent-child failure; approval revocation race; external effect without result checkpoint.

Pass/failure evidence: Score the reconstructed cause and timeline against the hidden truth; record unknown answers instead of guessing from absent logs.

Measurements: correct diagnosis, unsupported conclusions, time to reconstruct, evidence completeness.

### D09-04 — Retention, export, and tamper boundaries

Architecture mechanism: Retention policy and record ownership determine which later audit claims remain possible.

Controlled change: Rotate, prune, export, restart, and modify records under declared administrator and unprivileged roles.

Scenarios: retention boundary; export and reimport; redaction of synthetic secrets; record modification attempt.

Pass/failure evidence: Compare declared guarantees with retained event identity and content; plain diagnostics are not automatically tamper-evident audit storage.

Measurements: retained event coverage, export fidelity, redaction errors, tamper detection where promised.

## D10 — Maintainability and operability

V6 has real backup/restore, upgrade, and dependency tests. More depth requires recovery during concurrent writes, partial migrations, failed dependency publication, and operator diagnosis rather than command exit codes.

### D10-01 — Consistent backup during active work

Architecture mechanism: Configuration, databases, workspaces, and queued jobs may be captured at different logical moments.

Controlled change: Take supported backups while synthetic work updates each state class, then restore into a clean target.

Scenarios: idle snapshot; concurrent writes; queued work; interrupted backup.

Pass/failure evidence: Validate the declared snapshot consistency boundary and native service behavior; include externally stored workspaces only when explicitly in scope.

Measurements: inconsistent task states, missing promised artifacts, restore time, manual recovery actions.

### D10-02 — Upgrade and rollback after partial migration

Architecture mechanism: Application code and persisted schema may advance in separate steps, making binary rollback insufficient.

Controlled change: Interrupt the documented upgrade at each observable migration boundary and follow the documented recovery or rollback path.

Scenarios: before schema change; during schema change; after schema change before service ready; extension incompatible with new version.

Pass/failure evidence: Verify the supported rollback contract and data semantics; an unsupported downgrade must be explicit rather than silently corrupting state.

Measurements: unrecoverable states, data semantic changes, downtime, rollback steps.

### D10-03 — Dependency publication and repair

Architecture mechanism: A partial install, shared cache, or lock failure can affect later sessions even after the original setup process stops.

Controlled change: Inject download, checksum, disk, and publication failures using local fixtures and one owned dependency installation.

Scenarios: partial download; checksum mismatch; cache unavailable; installer interrupted before publication.

Pass/failure evidence: The previously usable generation must remain usable or fail visibly according to contract; no case may copy the whole shared environment by default.

Measurements: broken published generations, repair actions, residual bytes, independent-session availability.

### D10-04 — Diagnosis and operational burden

Architecture mechanism: A short command can conceal multiple manual decisions, privileged actions, or undocumented state repairs.

Controlled change: Give an operator a frozen runbook and injected configuration, database, and extension failures.

Scenarios: invalid configuration; state corruption; extension startup failure; storage exhaustion.

Pass/failure evidence: Record correct diagnosis, logical interventions, privilege requirements, and validated recovery; shell line count is not an effort metric.

Measurements: diagnostic accuracy, active operator time, logical interventions, validated service restoration.

## D11 — Compatibility

V6 explicitly limits compatibility to a finite protocol and package list and notes untested legacy SSE, expired MCP sessions, cancellation edges, and opaque reasoning signatures. Each external contract needs its own advertised/tested/unsupported record.

### D11-01 — MCP transport and content contracts

Architecture mechanism: Transport support and tool-result semantics are distinct compatibility layers.

Controlled change: Use a versioned local conformance fixture for each advertised transport and each content type.

Scenarios: stdio; Streamable HTTP; legacy HTTP/SSE when advertised; text, structured, resource, Unicode, and large results.

Pass/failure evidence: Validate parameter and content fidelity, structured errors, and full-result access; record unsupported transports separately from failures of an advertised contract.

Measurements: advertised contracts passed, content fidelity, semantic errors, required adapters.

### D11-02 — MCP session and cancellation lifecycle

Architecture mechanism: Reconnect, request identity, expiry, and cancellation can behave differently from successful steady-state calls.

Controlled change: Expire or disconnect an active synthetic MCP session and inject out-of-order or late responses.

Scenarios: expired session; reconnect during call; cancel in flight; late response after cancellation.

Pass/failure evidence: Match each response and effect to its request and session generation; rejected calls must not silently produce forbidden effects.

Measurements: request identity errors, duplicate effects, stale session use, cancellation fidelity.

### D11-03 — OAuth authorization lifecycle

Architecture mechanism: Discovery, grants, token refresh, and scope handling may be delegated to different integration layers.

Controlled change: Use a local synthetic authorization server and the exact OAuth profile advertised by the integration.

Scenarios: initial grant; token refresh; expired or revoked grant; insufficient scope.

Pass/failure evidence: Check the declared authorization profile and actual tool effect without real identity-provider credentials; do not call generic HTTP support OAuth compatibility.

Measurements: advertised flows passed, scope enforcement, refresh behavior, adapter requirements.

### D11-04 — AGENTS.md and external Skill inputs

Architecture mechanism: Instruction-file discovery and external Skill packaging can preserve file format while changing precedence or execution meaning.

Controlled change: Import the same versioned external guidance and Skill corpus, including declared path and precedence variants.

Scenarios: root and nested AGENTS.md; external Skill package; relative resource paths; conflicting or unsupported metadata.

Pass/failure evidence: Check which instructions and assets actually reach the task under documented precedence; importing files is not behavioral equivalence.

Measurements: declared formats passed, guidance precedence fidelity, asset resolution, conversion steps.

### D11-05 — External tools, plugins, and harnesses

Architecture mechanism: MCP tools, product-specific plugin SDKs, and external agent harnesses expose different contracts and ownership boundaries.

Controlled change: Use a declared external artifact corpus and identify the integration route required by each product.

Scenarios: MCP tool configuration; foreign plugin SDK package; external harness process; extension update and uninstall.

Pass/failure evidence: Record direct compatibility, documented adapter, core modification, or unsupported status separately; a callable tool is not full harness replacement.

Measurements: directly reusable artifacts, adapter scope, core changes, lifecycle fidelity.

### D11-06 — Model streaming and reasoning payloads

Architecture mechanism: Tool-call assembly, stream termination, and provider-specific reasoning fields can break otherwise accepted model protocols.

Controlled change: Replay versioned local transcripts with split chunks, malformed events, errors, and opaque provider fields.

Scenarios: fragmented tool-call arguments; stream ends before usage; provider error and retry; opaque reasoning field round trip.

Pass/failure evidence: Validate tool identity, arguments, visible completion, usage completeness, and declared provider semantics; deterministic replay says nothing about model reasoning quality.

Measurements: transcript contracts passed, argument corruption, premature completion, usage and opaque-field fidelity.

