# Practical two-layer evaluation plan

## Research question

The platform layer studies how a system hosts work: entry points, process and machine boundaries, communication, state and credential ownership, shared resources, failure propagation, and operations. The absence of a Gateway is itself a design choice. Identify which responsibilities move to the client, process, filesystem, or external service, then compare startup and idle cost, fault domains, isolation, and the cost of providing multiple entry points or remote access. Do not score a missing component as a failure. Compare actual validated deployments and list external components, versions, and cost separately.

The harness layer studies how one agent run is assembled and controlled: context assembly and compaction, session recovery, tool scheduling, approval and execution boundaries, cancellation and retries, extension, and execution traces. Reliability, security, performance, resource cost, extensibility, and observability are evaluation dimensions for each layer.

Use separate tracks: native product configurations; controlled harness experiments with the same model, tools, and budget where supported; and mechanism-specific investigation. Disclose uncontrolled factors. A shared model alone does not prove that a particular mechanism caused an observed difference.

## Six-dimension interpretation

Every item in [the status ledger](progress.json) identifies its primary dimensions. The homepage maps all six dimensions across both architectural layers. These are evidence relationships, not claims of full coverage or dimension-level scores. One observation can inform multiple dimensions: H05 can demonstrate conversation recovery and the trace available to diagnose it, but cannot establish effect safety without an independent effect ledger. P02 can locate credentials but does not by itself establish authorization or confidentiality. P04 examines integration but does not prove harness replacement. A final six-dimension assessment requires matching formal results, explicit deployment and model controls, and disclosure of missing or inapplicable capabilities.

## Before execution

Freeze product version, commit when available, entry point, operating system, configuration, model, and tools. DSH 0.2.2-alpha.2 is a preview package and its package integrity must be recorded. The frozen OpenClaw campaign's version applies only to its own evidence. Draw and validate each actual deployment and responsibility map. Record model substitution, tool integration, request visibility, fault injection, resume, and approval as native, public extension, external component, unsupported, untested, or unobservable. An adapter must not implement retries, deduplication, or permissions on the product's behalf.

## Initial work items

[First-wave protocols](first-wave-protocol.md) specify the first four scenarios and their limits. The remaining entries are research candidates, not verified common protocols. Run a feasibility check first, then freeze a formal protocol. Invalid units include unreached faults, adapter errors, and failed positive controls; retain genuine product failures.

| Layer | Work item | Minimum observation | Architecture value and boundary |
| --- | --- | --- | --- |
| Platform | P01 Fault domain | Terminate an entry, core, or tool process during the same task; record survival and recovery | Reveals ownership and fault propagation; do not invent a Gateway where none exists |
| Platform | P02 State and deployment | Locate session, workspace, credentials, and logs; inspect recovery after restart | Separates process and persistence ownership, including external components |
| Platform | P03 Resources and concurrency | Measure idle, one-task, and multi-task resources, completion, and failures | Quantifies the cost of lifecycle and sharing; calibrate load before ranking |
| Platform | P04 Access and operations | Submit, observe, cancel, and resume through native entry points; record setup and dependencies | Identifies integration and operational responsibilities, including the cost of missing remote access |
| Harness | H03 Compaction | Trigger native compaction in a task with early constraints and an updated rule | Measures constraint retention, task quality, and cost; invisible inputs limit attribution |
| Harness | H04 Large outputs | Put checksums at the beginning, middle, and end of outputs, with and without a retrievable file | Tests visibility and recovery; failure alone does not establish truncation as the cause |
| Harness | H05 Recovery | Interrupt before and after an externally logged side effect and resume | Separates conversation recovery from effects, retries, and ownership of idempotency |
| Harness | H08 Scheduling | Use independent reads, a dependency chain, and conflicting writes | Reveals ordering, concurrency, and partial failure; separate scripted from real-model results |
| Harness | H11 Approval | Change parameters or revoke policy around an approval and record actual dispatch | Tests whether authorization covers the executed action; document alternative native safeguards |
| Harness | H17 Trace reconstruction | Blindly reconstruct model calls, approval, tool failure, and effects from native records | Measures causal visibility; the external ledger is a verifier, not a native log |

## Execution and evidence

For each unit retain version, configuration hash, fixture, task, fault reachability, timing boundaries, native events, external effect ledger, acceptance, usage completeness, and adapter responsibilities. Use synthetic secrets. Begin with at least three independent units for deterministic mechanisms and six for performance; interleave product order. Real-model work needs multiple independent task instances and repeated runs. Freeze sample sizes and timeouts after calibration. Small samples do not justify tail or population rankings; unobserved values are unknown, not zero.

Complete entry-point checks and deployment maps; calibrate common minimum scenarios; freeze model, permissions, budgets, and acceptance; then run formal units and expand where evidence warrants. Assess old OpenClaw results per subscenario: inherit an observation only when evidence and protocol match; otherwise retain it as a historical baseline or reuse only the facilities. Do not combine historical performance or success rates with a new matched batch.

Each conclusion links mechanism, conditions, observations, task impact, cost, and applicability. Present platform and harness results separately. Keep failure, unsupported, and untested distinct. Do not attribute external-component behavior to the product, or task success directly to architecture.
