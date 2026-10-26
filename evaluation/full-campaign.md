# Full experiment campaign

The current instruction is experiment first: implement the complete frozen scope, execute it, audit completion, and only then produce the unified source-backed architecture interpretation. The [frozen plan](campaigns/full-20261026/plan.json) preserves all 60 experiment families and 257 scenarios across exactly six dimensions. OpenClaw is the only product. Earlier exploratory pilots do not satisfy this campaign's coverage.

```sh
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

At campaign creation all 257 scenarios are unexecuted. The current adapter set still consists of exploratory pilots. Publishing this plan or passing repository CI does not mean the native full suite is implemented or executed.
