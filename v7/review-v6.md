# Review of the V6 evaluation

## What went wrong in the interpretation

The earlier review treated coverage of eleven headings as sufficient support for broad architectural conclusions. It was too quick to turn an observed difference into a general property of a framework. A result from one execution path cannot characterize every plugin, tool, provider, or harness path, and a latency difference does not identify its cause without phase and runtime attribution.

This is not a claim that V6 had only fourteen test executions. The frozen protocol defines fourteen experiment families, thirty-three weighted criteria, repeated fresh profiles, matched tool tests, fault probes, real task runs, source references, and selected causal controls. Those are useful foundations. The weakness is uneven depth at architectural boundaries and the compression of distinct outcomes into broad grades.

## Evidence reviewed

The review uses the frozen V6 protocol and scripts, plus the separately retained `observations.json` and `final-grades.json`. [The evidence review record](design/v6-evidence-review.json) identifies those artifacts by SHA-256 without copying raw logs or result databases into this repository.

Thirty of thirty-three metrics have entries in the retained observations. An entry is not necessarily a complete or decisive measurement: for example, the migration metric includes dependency reconstruction but lacks its required native cross-OS case. The final resource/cost and portability dimensions remain ungraded. Native Windows execution and colleague review are recorded as pending.

## Specific gaps and changes

| Area | What V6 already contains | What the next design must resolve |
| --- | --- | --- |
| Recovery | Restart, plugin faults, child work, duplicate-effect checks | Sweep durable-admission and effect-acknowledgment boundaries; separate correctness, automation, service availability, and human intervention |
| Security | Actual filesystem/network/process probes and allowed-operation controls | Enumerate every execution surface, inherited credentials, revocation lifetime, tenant reuse, and setup failure |
| Control | Policy-load failures, approval modes, cancellation, and delegation | Race policy changes against dispatch and enforce shared budgets across concurrent descendants |
| Performance | Matched task latency, cold/warm gateways, MCP critical paths | Attribute preparation, queueing, runtime CPU, event-loop delay, connection locks, and external waiting separately |
| Resources | Actual usage reconciliation, process-tree checks, reuse profiles | Measure idle and marginal costs, component reuse, amortization horizons, and disk/inode amplification; do not equate machine memory with API price |
| Scale | Concurrency levels through sixteen and two same-host isolated nodes | Add open-loop overload, shared-state contention, independent hosts, and bounded sustained runs |
| Extensibility | Real public extension routes and lifecycle checks | Separate tools, provider routing, context replacement, and full harness ownership; test active-call replacement and version skew |
| Portability | Changed Linux paths/UID and dependency reconstruction | Test identity changes one factor at a time and require actual native target execution for cross-OS claims |
| Observability | Native/truth separation and matched brief collector outages | Reconstruct exact authorization scope; test publisher restart, buffer exhaustion, retention, export, and blind diagnosis |
| Operations | Real restore, upgrade, and dependency cases | Test backups during writes, partial migrations, interrupted generation publication, and operator diagnosis |
| Compatibility | A finite, explicit protocol/content/package list | Add expired MCP sessions, cancellation, declared legacy transport support, OAuth lifecycles, external guidance/Skill formats, external plugin/harness contracts, and opaque model payloads |

The retained V6 evidence explicitly leaves the complete intervention-time contract, native cross-OS case, and full audit retention/export contract unresolved. It also states that legacy MCP SSE, expired-session/cancellation edge cases, and opaque reasoning signatures were not separately exercised. V7 makes these gaps visible rather than converting them into general product claims.

## What must change in the reporting

A safe stop can preserve correctness while requiring manual work. An automatically resumed task can improve availability while repeating an external effect. Those outcomes must not disappear into one recovery verdict. Likewise, a separate process can limit crash impact without restricting its filesystem or network authority.

For every architecture claim, report the observed outcome, the concrete process/thread/state/connection mechanism, a matched intervention when feasible, and the conditions under which the advantage reverses. Source inspection alone supports a mechanism hypothesis; it does not replace an experiment. V6 grades remain historical results under their frozen rubric, not V7 findings.
