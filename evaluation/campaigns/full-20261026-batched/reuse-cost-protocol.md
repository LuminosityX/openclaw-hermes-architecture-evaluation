# COST-03: real reuse, learning cost and stale-rule effects

Each of the four frozen scenarios has six independent paired units. Baseline and reuse execute the exact same independently judged orders and active rule versions, using separate native state/workspace directories and a fresh native session for every delivery. Arm order alternates by unit to expose warm-cache/order effects. Runtime dependencies are shared read-only and never copied per case.

The baseline can read a versioned public rulebook. The reuse arm first asks the actual agent to derive a concise version-1 guide and save root `AGENTS.md` with the native `write` tool. No evaluator-written summary or hidden answer enters a real-model run. All later inputs, rules, generated assets, task file calls, artifact hashes, endpoint deadlines, model usage and resources are recorded. Native source-marker observations establish whether the learned guide actually enters later fresh-session model contexts; golden wiring answers alone cannot hide absent context.

| Scenario | Later deliveries in each arm |
| --- | ---: |
| S01 | 1 |
| S02 | 5 |
| S03 | 20 |
| S04 | 5; active rule changes from version 1 to version 2 after the first two, while the learned asset remains version 1 |

Policy credits use explicit integer arithmetic. Every delivery must independently match order identity, active version and computed credits, preserve integer types, retain immutable reference files and meet its 25-second endpoint deadline. Each delivery has a unique output filename so late work cannot be scored as another task's artifact. The learned guide must exist, have the registered marker, and complete its learning call within 60 seconds. The compound unit is bounded to 1,150 seconds for acceptance, 1,200 seconds for the hosted namespace, 128 protocol requests and 4,096 output tokens per request. These are experimental conditions, not a monetary ceiling.

`series.json` is an evaluator aggregation of verbatim agent-written per-delivery files and endpoint records, not a model-produced claim of success. The host judges every file against its private independent policy oracle. Six paired units across all horizons request 372 later deliveries plus 24 learning tasks; they still represent only four scenario IDs and 24 independent campaign observations.

Provider usage is real in formal runs. Learning, retries and failed requests stay in the reuse numerator; baseline and reuse normalize by independently accepted deliveries. Auxiliary/unattributed requests and missing counters remain explicit and also remain in campaign totals. Cache hits/misses partition inclusive input. Actual invoiced USD and a monetary break-even point remain unknown, rather than being inferred from synthetic usage or treated as zero. This does not complete provider-invoice reconciliation in COST-07.

Whole-family native golden calibration precedes paid work. The complete source rulebook, golden fixtures and oracle remain versioned; golden artifacts and synthetic token counters never become formal cost or model-quality data. Every dependency installation, learned asset and native state lives on a disposable GitHub runner. Bounded raw evidence stays in hosted artifacts; compact accepted records use lossless compression and remain below the local campaign evidence budget. Architectural interpretation remains deferred until the complete campaign audit passes.
