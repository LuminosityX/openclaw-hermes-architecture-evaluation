# Service path and public trace experiments

These adapters add PERF-01, PERF-02, PERF-04, COST-02, COST-04 and OBS-07,
covering the exact 25 scenario IDs in the frozen campaign plan. Each family
first completes native calibration on the hosted runner, then executes all
three or six prescribed fresh independent units at identical controller hashes.
Calibration observations never become formal observations. Product assertion
failures remain data; fixture or invocation failures block that unit.

The runtime, official provider plugin and lockfile are unchanged. The provider
is a local deterministic fixture. Independent receipts establish whether work
actually committed. Synthetic nonzero usage in OBS-07 is an arithmetic and
attribution oracle; it provides no real token cost or problem-solving score.

PERF-01 compares 1/128 actual registered tool schemas, short history against
twelve actual same-session tool/result turns, and cold/warm run-owned JITI
cache. Native provider input counts and bytes are recorded. PERF-02 compares
the same receipt operation with a 600 ms synchronous plugin CPU loop or an
asynchronous timer, and six ordered same-session turns versus six simultaneously
offered independent sessions. PERF-04 overlaps an 800 ms external tool wait
with short tasks, a 128-tool catalogue, a burst of eight short tasks, or public
session cancellation. The uncooperative external effect can survive abort; it
must not be represented as successful task completion after cancellation.

HTTP completion latency, provider/tool/effect timestamps, product process
counters and a 50 ms independent `/readyz` responsiveness probe are separate
measurements. Thread user/system CPU and kernel schedstat running/runqueue
counters are sampled at the same interval; first/last native thread samples
are retained with probe distributions. Exited short-lived threads may be missed.
The non-streaming client does not expose first-text latency; no such measurement
is fabricated. No arbitrary speedup threshold is treated as product correctness.

COST-02 records startup and task phases with explicitly cold/preserved JITI
cache, a reused process, or three native process/plugin-registration generations.
Node compile caching remains disabled throughout. COST-04 records apparent
bytes, allocated blocks, file/directory inodes and open-but-deleted descriptors
for owned runtime state, with the owned cache measured separately. The interrupted
setup case kills an actual Gateway startup after 200 ms and validates a fresh
startup and task on that state. This tests native service/state setup, not npm
installer publication (which belongs to REL-12). Evidence hashes are retained
before deleting state. The shared installation is read-only and never copied.

OBS-07 uses public wire protocol 4 and synthetic Ed25519 device authentication,
following the already validated Gateway authentication fixture. Native
`chat.history` is the display-normalized documented export, not assumed to be
the complete canonical transcript. JSON export is parsed by an independent
consumer; this does not claim native session import. Exact tool-error diagnosis
receives only native export bytes before the external truth ledger is scored;
it is a rule-based reconstruction, not a human usability study. Usage is queried
for the exact task session and reconciled with independent nonzero fixture
reports. Read-only and zero-scope paired-device connections exercise actual
trace access. Debug versus silent native file logging uses matched correctness
tasks after restart; the external resource sampler is identical in both arms.
One matched pair per independent unit cannot alone establish statistical
significance or a universal observer overhead.

Usage queries that explicitly report `computing` or `refreshing` are polled for
at most twenty seconds, retaining the intermediate states. Temporary zero totals
are not treated as a finalized missing-usage observation. The original immediate
oracle incident in run 40306085535 is quarantined in `validity-incidents.json`;
its native evidence remains unchanged, and only the affected pending scenario
is formally rerun after new whole-family calibration.

Public contracts are pinned to OpenClaw source
`157d8c2bc3ea2fa183afdc11088e69690bf8e64e`:

- `docs/gateway/protocol/rpc-session-control.md`
- `packages/gateway-protocol/src/schema/logs-chat.ts`
- `packages/gateway-protocol/src/schema/sessions.ts`
- `packages/gateway-client/src/device-auth.ts`

No core edits or private imports are used. Heavy installation and execution run
only on disposable GitHub-hosted workers. Each job always removes its runtime,
cache, proof copies and state; bounded raw artifacts expire after 30 days.
Local campaign retention remains capped at 4 MiB.
