# Evaluation methodology

V6 compares the pinned OpenClaw and Hermes releases under controlled task, fault, policy, and integration scenarios. The [frozen protocol](../../v6/protocol/protocol_v1.json) is the authoritative experiment specification; this document provides an English guide without changing that specification.

## Architecture dimensions

| ID | Dimension | Architectural question |
| --- | --- | --- |
| D01 | Reliability and recoverability | Who owns task progress, and which records support restart, reconciliation, or safe retry? |
| D02 | Security and isolation | Which boundaries are enforced by the operating system, containers, or proxies, and which components retain host privileges? |
| D03 | Architectural control | Where are policies enforced, and are they checked again after delegation, restart, or a change of entry point? |
| D04 | Performance and responsiveness | How much waiting comes from model calls, admission queues, tool serialization, state handling, and startup? |
| D05 | Resource and cost efficiency | How do context construction, call counts, resident processes, and shared state affect measured resource use and cost? |
| D06 | Scalability | Does added capacity expand execution resources, and what limits admission, state access, connections, or queues? |
| D07 | Modifiability and extensibility | Which changes use public interfaces, and which require core changes or a maintained product fork? |
| D08 | Portability | How do state identity, paths, authentication, dependencies, and service bindings affect migration? |
| D09 | Observability and auditability | Where are records produced and stored, and which execution or failure paths can leave gaps? |
| D10 | Maintainability and operability | How are dependencies, upgrades, rollback, backups, and extension lifecycles managed? |
| D11 | Compatibility | At which layers are external protocols, extension formats, and persisted data adapted? |

## Workloads and controls

The task fixtures cover regression repair in a pinned real project, feature delivery, data reconciliation against supplied rules, and a multistep service workflow. Separate controllers examine faults, security boundaries, policies, tool protocols, extensions, migration, state operations, and observability.

Real-model tasks and deterministic protocol fixtures serve different purposes. Deterministic fixtures prescribe requests while installed products execute the operations; they are not evidence about model reasoning quality. Controlled ablations, including the [Hermes MCP lock patch](../../v6/patches/hermes-mcp-lock-ablation.patch), are counterfactual experiments rather than baseline product behavior.

## Scoring and evidence

The [scorer](../../v6/protocol/score_protocol.py) consumes paired observations and explicit evidence references. Quantitative comparisons require sufficient independent units and preserve clustering. Functional comparisons require repeated acceptance outcomes. Missing measurements and failed validity gates must not be converted into parity or a product failure.

The protocol's grade values are retained as `强`, `中`, and `弱` (strong, medium, and weak). A missing grade remains missing. These grades are relative to the frozen criteria and evaluated product set, not universal rankings of current releases.

## What repository checks establish

Offline checks establish that the retained files match their manifests, references resolve, supported source files parse, and the scorer's synthetic decision-rule tests pass. They do not establish product performance, successful model calls, runtime recovery, isolation effectiveness, or native Windows execution. Those conclusions require the separately retained execution evidence.
