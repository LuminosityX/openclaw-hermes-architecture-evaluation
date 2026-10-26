# Current evaluation methodology

The current subject is OpenClaw as a task-execution framework. Results are organized into exactly six dimensions in the [matrix](../evaluation/design/evaluation-matrix.json): reliability, security, performance, resource usage/cost, extensibility, and observability. The former eleven-dimension OpenClaw/Hermes comparison is [historical](history/v6-methodology.md).

## Task outcomes and mechanism tests

Performance includes the ability to solve the problem: acceptance of coding, data, research and multistep workflow deliverables, constraint retention, timeout/failure rate and success under concurrency. A fast incorrect answer is not successful throughput. Count attempted tasks, accepted tasks, all failures/cancellations and correct goodput. Report latency distributions alongside sample sizes and timeouts; never silently remove slow or failed requests.

Real-model workloads evaluate task completion and model-dependent attacks. Pin model/provider, decoding settings, tools, context and acceptance checks. Deterministic provider/tool fixtures isolate protocol handling, retry logic, authority boundaries and scheduling. They cannot establish reasoning quality or real-model prompt-injection resistance. Record model failures, framework failures, unsupported capabilities and harness errors separately.

## Six reporting dimensions

Reliability covers acknowledged task durability, effect duplication, state continuity, provider/tool failures, cancellation, restore and dependency failure. Security covers synthetic personal-data disclosure, permission and session boundaries, untrusted instructions, local network attack fixtures and control-plane access. Extensions require documented interfaces rather than assuming every plugin is sandboxed. Observability asks whether a reviewer can actually access and use the trajectory to diagnose behavior, including unavailable events and required privileges.

Resources include complete process/container membership: CPU time/throttling, memory RSS/PSS/cgroup peak and swap, allocated/apparent disk bytes, inodes, IO, network, processes, threads and descriptors. Separate idle, incremental, peak, sustained and residual usage. Token cost includes successful and failed requests, retries, delegation, auxiliary calls and cache behavior. Hardware consumption, calculated token estimates and provider-reported charges are separate measurements.

## Experimental controls

Each run pins OpenClaw source/version, effective configuration, plugins/hooks, execution surface, host and fixture revisions. Use fresh state or documented resets. Requests sharing a service are repeated observations within that unit; do not inflate independent samples. Choose repetitions, concurrency levels, acceptance thresholds and stopping rules before execution, and preserve incomplete evidence.

Keep an independent outcome/event ledger separate from native traces. Faults occur at observable task boundaries; fixture validation must demonstrate the intended failure. Changes to one supported configuration or mechanism enable controlled interventions. A patched runtime is a counterfactual and source inspection is a mechanism hypothesis, not an executed outcome. Unsupported advertised contracts and absent advertised support require different labels.

## Evidence and current status

Architecture conclusions compose cases using the [cross-dimensional study protocol](../evaluation/architecture-studies.md). The three-study first wave isolates supported session concurrency and sandbox-scope settings, then compares plugin execution boundaries with explicit route confounders. Other studies address trace detail, context reuse, retries and Gateway ownership. Six dimensions remain reporting axes rather than six independent explanations. Report design intent, measured behavior and inference limits separately.

The full 60-family coverage plan remains incomplete. A [bounded native adapter](../evaluation/runner/README.md) implements first-wave exploratory pilots with a deterministic provider and actual OpenClaw Gateway/tool execution. Product conclusions still require valid fixtures, independent evidence verification and appropriate analysis; these small pilots do not establish real-model task quality or complete-family results. CI validates repository/tool behavior without running the local pilots. See the [measurement contract](../evaluation/measurement-contract.md) for evidence and price requirements. Historical V6 grades remain scoped to their frozen two-product rubric.
