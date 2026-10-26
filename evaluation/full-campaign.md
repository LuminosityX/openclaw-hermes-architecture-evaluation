# Full experiment campaign

The current instruction is experiment first: execute the complete frozen scope, audit completion, and only then produce the unified source-backed architecture interpretation. The active [batched plan](campaigns/full-20261026-batched/plan.json) preserves all 60 experiment families and 257 scenarios across exactly six dimensions. It supersedes the [original plan](campaigns/full-20261026/plan.json) only in execution scheduling: each calibrated family may complete its prescribed formal repetitions while remaining adapters are built. Scope, target, independent-unit counts, acceptance contracts, resource policy and the whole-campaign analysis gate are unchanged. No formal observations existed when the plan was superseded. OpenClaw is the only product. Earlier exploratory pilots do not satisfy this campaign's coverage.

```sh
python3 evaluation/tools/adapter_readiness.py
python3 evaluation/tools/campaign.py status
python3 evaluation/tools/campaign.py seal
```

`seal` fails while any scenario is not run, partial, blocked, or affected by an unresolved harness failure. Product failures count as completed experiments when the required independent observations and acceptance evidence exist. Verified native nonapplicability requires a probe and a contract tied to the pinned source revision; missing adapters, environments, credentials or measurements do not qualify. These exclusions are reported separately from measured coverage. The gate validates submitted evidence records; it cannot establish that a dishonest assertion describes a real experiment. Original receipts and provenance remain review requirements.

The frozen plan prescribes six independent units for performance/resource cases and three for other dimensions. Per-scenario records must bind the plan hash, actual installed version/commit, hosted run ID, unit and evidence-backed acceptance assertions. The original matrix remains the design inventory; actual campaign progress comes from accepted execution records.

## Model connection

The selected model is `deepseek-flash` at the official DeepSeek endpoint. The user explicitly requested **no campaign monetary ceiling**. Finite task timeouts, retries, token limits and hardware limits remain recorded experimental conditions, rather than a hidden monetary ceiling.

Configure a repository Actions secret named `DEEPSEEK_API_KEY` at [repository Actions secrets](https://github.com/zyw02/openclaw-hermes-architecture-evaluation/settings/secrets/actions). If that page is unavailable, use an account with repository administration rights, or run this interactive command in your own authenticated terminal:

```sh
gh secret set DEEPSEEK_API_KEY --repo zyw02/openclaw-hermes-architecture-evaluation
```

Do not put the value in a command argument, issue, committed file or chat. The [connection workflow](../.github/workflows/deepseek-preflight.yml) queries authenticated model discovery only. It requests no completion tokens and retains only selected model metadata. A successful connection check is not an experiment result.

DeepSeek exposes a moving alias, so capture discovery metadata, the returned model identifier and usage for real calls. Record unknown billing categories and missing invoice reconciliation as unknown; do not invent actual charges from zero fixture usage or confuse a price-based estimate with an invoice.

## Storage and execution

Use disposable hosted runners, share one exact runtime installation within each shard, and delete that shard's owned installation/cache/state after evidence collection. Do not install a second OpenClaw runtime or copy dependency trees to the local workspace. The full campaign's compact local evidence budget is 4 MiB; runtime state and raw private trajectories are excluded. Larger synthetic evidence remains bounded in hosted artifacts and must not be pulled locally without a specific need.

The [formal batches](campaigns/full-20261026-batched/README.md) currently complete 83 scenarios and 378 independent observations, leaving 174 incomplete. The live `campaign.py status` audit is authoritative. [Validity incidents](campaigns/full-20261026-batched/validity-incidents.json) quarantine invalid fixture/intervention/oracle observations while preserving their original provenance. Only affected pending scenarios are rerun. Formal real-model PERF-09 observations remain separate from deterministic mechanism observations and development calibration.

The added load/resource conditions use finite batches: eight requests and two active native slots for admission/overload; one versus independent sessions for contention; up to sixteen simultaneously held tool requests for resident memory. The long-state-transaction fixture holds an actual native transcript SQLite write transaction for one second and rolls it back without changing records. A delayed-commit fixture commits the external effect before delaying its acknowledgment. These conditions must be disclosed with results rather than described as unrestricted production load.

Hardware checkpoints retain product-descendant PSS/RSS/CPU/IO/process/thread/descriptor counters, separate run-cgroup counters, state blocks/files, and isolated-loopback traffic. The cgroup includes the fixture, controller and tmpfs; its peak is cumulative over the owned run. The IO task uses a 256 KiB tmpfs write/read and loopback HTTP payload, not a block-storage benchmark. Unavailable counters remain null with a reason. Plugin composition uses two tiny local ESM dependency fixtures with different versions, public tool registration and per-plugin configuration; it requires no core edits or private imports.

`adapter_readiness.py` compares preparation proofs with the current controller hashes. A shared-controller change invalidates older preparation proofs until recalibrated. `--require-complete` still reports readiness of the entire scope. The active batched plan permits formal execution only when every scenario in the selected family has current native validation. Both the native and paid task controllers enforce that family gate. The original plan's all-adapters gate remains its recorded policy. Development calibration requires an explicit flag, carries `full_campaign_coverage: false`, and is rejected by the campaign completion audit; calibration output cannot be relabelled as formal observations.

Preparation readiness applies to new executions using current controller files. The same report separately shows completed formal scenarios and independent observations under their recorded controller commits. Later additions to a shared wrapper do not erase previously recorded execution. A demonstrated validity defect still requires explicit supersession of affected observations; a stale preparation proof cannot authorize another paid or native formal run.

The [campaign workflow](../.github/workflows/campaign-batches.yml) runs new formal executions. Its `mechanisms` category repeats every ready native family for all three or six independent units, sharing one hosted runtime across those units. Its `tasks` category runs six real `deepseek-flash` tasks for each of the five PERF-09 scenarios, with hidden host-side acceptance. Product failures remain completed observations; harness failures remain incomplete. Original synthetic evidence is bounded to 8 MiB per hosted shard and retained for 30 days. Compact result records and artifact hashes are retained locally within the existing 4 MiB campaign limit. The final `seal` gate still requires the whole 257-scenario scope.

Formal shards use `npm ci` with the retained [full dependency lock](campaigns/full-20261026/preparation/package-lock-d145b4db4bce.json), SHA-256 `d145b4db4bce891044af6d2a45819d5cb965160856873858e6c124f249f8ac8a`. Each shard verifies package integrity and reuses that one installation for all its units. Preparation installations keep their own provenance and are not silently treated as the same dependency condition.

After a formal hosted run finishes, retain only compact records and original-artifact hashes with `python3 evaluation/tools/retain_campaign_results.py --run-id RUN_ID`. The tool reads bounded ZIP archives in memory, verifies original evidence paths and native digests, rejects duplicate independent units and checks the entire local campaign footprint before writing. It never downloads or extracts runtime dependencies or raw trajectories to local disk.

The task runner uses the pinned official [DeepSeek provider plugin](design/deepseek-plugin-pin.json). Real task execution defaults to its thinking-enabled condition with a declared 16,384 output-token limit per request, 16 model protocol requests per task, and a 180-second task deadline. These finite workload conditions are recorded separately from monetary authorization. The initial provider plumbing check instead uses the explicitly recorded non-thinking 4,096-token condition. Do not compare their outcomes as matched task-quality conditions. Golden transcript calibration calls no real provider.

Publishing these adapters or passing repository CI does not mean the native full suite is implemented or executed.

The [remaining-mechanisms workflow](../.github/workflows/remaining-mechanisms.yml) calibrates each selected family against the native pinned runtime, then runs its prescribed independent units at the same hashes in the same hosted shard. Family-level concurrency avoids replacing unrelated queued batches. Optional explicit pending scenario IDs allow validity repairs without repeating accepted observations. Existing accepted scenarios are rejected before installation and by the formal controller.
