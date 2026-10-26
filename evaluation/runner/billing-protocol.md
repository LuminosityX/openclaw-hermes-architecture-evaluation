# Real native provider accounting

Each calibration and formal unit uses the real user-selected DeepSeek Flash via
an isolated native Gateway and the fixed-origin host-only relay. Credentials do
not enter the agent namespace. Calibration is explicitly excluded from formal
counts; formal execution uses the frozen six independent units per scenario.

Scenarios exercise a successful arithmetic task; an intentionally unanswerable
withheld-information task; a real completed upstream reply discarded with HTTP
503 before native retry; actual native delegation requested from a real model;
two fresh sessions with an identical long prefix; and thinking-enabled output.
The failure scenario is not an injected cancellation. The retry scenario does not
pretend an upstream HTTP error itself was billed: the discarded reply has actual
successful provider metadata and is included alongside subsequent attempts.

All responses are buffered to a strict finite byte bound before forwarding in
this accounting-only adapter, including controls. This allows accounting for a
lost reply without losing its upstream usage. These timings are not streaming
performance measurements. No upstream prompts, responses or reasoning text enter
the provider ledger; synthetic task prompts/native replies remain native evidence.

Unknown usage, native attribution, provider-reported USD and invoices remain
unknown. A repeated prefix does not guarantee cache admission. Missing cache
write counters are not fabricated. Input already includes cache hit/miss subsets;
output already includes reasoning. A separately dated official price snapshot
produces estimates, with a range for weekday peak windows when Chinese holiday
status is unresolved. No absolute account balance is fetched or published and
no exclusive-account-use assumption is made.
