# OpenClaw measurement contract

## Scope and experimental units

Only OpenClaw is in the current evaluation. Each run records exact product version/source commit, entry point, effective configuration, state schema, plugin and hook revisions, model/provider and settings, task/fixture revision, host topology and environment ownership. Historical V6 pins are references, not default targets. No product experiment is enabled by the design or plan-selection CLI.

An independently initialized service, state profile, connection or host is the experimental unit as appropriate. Requests sharing one unit are repeated observations. Predeclare repetitions, workload sizes, latency quantiles, timeouts, equivalence margins and stopping rules. Keep failed, rejected, cancelled and incomplete runs in denominators. Small samples or missing tails cannot support invented p99 precision.

## Evidence and result records

Keep native traces separate from an independently timestamped event/effect ledger. Record run/task/attempt IDs; trace/span/parent IDs; provider request ID; process/thread identities; queue admission/dispatch; authorization policy version and scope; tool arguments/result/error; hook lifecycle; retries; cancellation; checkpoint and external effect IDs. Redact synthetic secrets in public artifacts. Preserve available model request/response metadata; private internal model reasoning is not required for observability.

Every measurement carries value, unit, sample window, collector/source, component scope, and evidence reference. A missing or unavailable value is `null` with a reason, never zero. Required metric definitions are listed per dimension in the [matrix](design/evaluation-matrix.json); each case declares which apply. Mark non-applicable counters explicitly. Result labels are `pass`, `fail`, `unsupported`, `not-run`, `inconclusive`, and `harness-error`. Plans and fixture checks never count as product runs.

Native record loss, collector/export loss and actual task loss are distinct. Withhold the independent oracle from blind diagnosis. A response or approval record alone does not prove a committed task, correct effect or complete authorization scope. Synchronize faults with admission, durable commit, approval, dispatch, external commit, persistence and acknowledgment boundaries.

## Task quality, latency and concurrency

Use versioned coding, data reconciliation, source-grounded research and multistep workflow tasks with independently hidden artifact/effect checks. Record accepted/attempted tasks, task success rate, first output and completion latency, queue wait, offered/admitted rate, correct goodput and sustainable concurrency. Report quality and timeliness together; fast incorrect answers are not goodput. Distinguish framework overhead, model waiting, tool execution, state locks and queueing.

Real-model task capability and prompt-injection susceptibility require actual model runs under pinned settings and explicit budgets. Local transcripts validate transport, mechanisms and authority enforcement only. Freeze model responses in deterministic controls; change one mechanism at a time. Private patches are labeled counterfactuals, separate from native OpenClaw behavior.

## Privacy and network boundaries

Use synthetic personal-data/secret canaries in prompts, attachments, memory, cache, plugins and exports. Independently inspect authorized and denied sinks, cross-session access, declared retention/deletion and redaction. Probe network boundaries in owned local fixtures, including controlled DNS/redirects, metadata stand-ins and gateway authentication. No test needs real user data or third-party attack traffic. A refusal message, process boundary or HTTP status alone does not establish enforcement.

## Hardware resource accounting

Sample the gateway, worker/tool descendants and relevant containers/cgroups at baseline, idle, active, peak, sustained, drain and cleanup checkpoints. Record collector interval and observer overhead. Shared installation/cache costs and per-run writable costs have distinct ownership; do not double count shared processes or sum RSS as physical memory.

Required counters include user/system CPU seconds and throttled CPU time; process RSS peak and sampled PSS; cgroup memory peak and swap; disk allocated/apparent bytes and inodes; read/write bytes and IO wait; network sent/received bytes; process/thread counts and open descriptors; residual disk after cleanup. RSS, PSS and cgroup totals are separate views, not additive values. IO-wait attribution must identify its collector and scope; unsupported platforms/counters remain null with reasons.

Capture idle baseline, marginal per-session/task use, peak, growth slope during sustained load and residuals. Budgets include dependency installations, caches, logs, writable fault generations and retained evidence. Track open-but-deleted files and surviving processes. Cleanup is limited to manifest-owned roots after evidence preservation; do not use personal caches as invisible state.

## Token usage and USD cost

Include every provider call: successful, failed, cancelled, retried, delegated, fallback, learning/memory and other auxiliary calls. Join requests to task/attempt IDs, preserving unknown or unbilled usage. Keep provider-reported charges, token-price calculations, external tool fees and hardware/hosting estimates separate. Record currency, model/provider, billing scope, effective price date and source. A calculated price is an estimate, not an invoice.

The offline `tools/costs.py` accepts one normalized provider/model group at one price snapshot:

```json
{
  "provider": "provider-id",
  "model": "model-id",
  "complete": true,
  "input_tokens": 1000,
  "output_tokens": 200,
  "cache_read_tokens": 300,
  "cache_write_tokens": 100,
  "reasoning_tokens": 50,
  "provider_reported_cost_usd": null
}
```

These numbers illustrate the input shape, not a measured run. Input totals include cache read/write, whose categories must be disjoint; output totals include reasoning. Provider adapters must normalize their native usage into these semantics. Unknown subcounts stay null; zero means verified zero. Usage from multiple requests is complete only if every request, including failures and retries, is accounted for. Reject subcounts exceeding totals.

The pricing document requires `provider`, `model`, `currency: "USD"`, `billing_scheme: "linear-token-categories"`, an ISO `effective_date`, a nonempty `source` and `usd_per_million_tokens`. Rates are nonnegative decimal strings for `uncached_input`, `cache_read_input`, `cache_write_input`, `visible_output`, and `reasoning_output`. A zero rate must be explicitly supplied when a used category is free. No price defaults are provided; tiered, time-dependent or other billing needs its own calculator.

Uncached input = input total minus cache read and cache write. Visible output = output total minus reasoning. Sum each disjoint category times its own USD-per-million rate divided by 1,000,000. The calculator uses decimal arithmetic and keeps `provider_reported_cost_usd` separate from `calculated_cost_usd`; its scope is model token charges only. `cost_per_accepted_task_usd` divides that total, including failed-attempt spend, by accepted task count. Zero accepted tasks or an unknown denominator yields null, not a zero unit cost. Missing usage or a used category's price yields null with a reason. Non-token fees and infrastructure cost are not silently included.

## Extension and trace evidence

For plugins and hooks, report documented public interfaces, private API dependencies, core files changed, registration/order/mutation/error semantics, compatibility and cleanup. Test supported hook points; unavailable capabilities are explicit. Tool/provider routing alone does not prove full agent-loop replacement.

For observability, measure event/argument/result/error availability, parent/child and provider-request linkage, export fidelity, retention, redaction, required permissions and blind fault-diagnosis accuracy/time. Compare observer-enabled and disabled controls. A large log volume is not proof that an operator can reconstruct agent behavior.

## Execution gates

Cross-dimensional architecture claims follow the [architecture study protocol](architecture-studies.md). A measured tradeoff needs supported benefit and cost in the same controlled workload; source evidence of design intent is a separate claim. Distinguish native config changes, topology/route boundary comparisons and patched counterfactuals. Preregister independent units, meaningful-difference margins, confounders, reversal workloads and hashed evidence artifacts before execution. Metadata validation never certifies product results or authorizes spending.

For the active [full campaign](full-campaign.md), `deepseek-flash` is selected and the user explicitly authorized no monetary ceiling. Keep per-task time/retry/token/hardware limits as declared experimental conditions. Do not ask for a monetary ceiling again.

Cases advance through planned, fixture-validated, adapter-validated, executed, evidence-verified and reviewed stages. Declare resource and real-usage budgets before execution; historical controller authorization does not supply them. Current CI validates design and tooling only. No numeric product score, statistical effect or architecture conclusion is generated from plan completeness.
