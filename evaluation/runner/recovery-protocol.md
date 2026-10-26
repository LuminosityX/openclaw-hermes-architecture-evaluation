# Native recovery and operator-confirmation conditions

REL-04 exercises four actual interventions: a reference plugin's once-only
`process.exit(42)`, a native stdio MCP worker's `os._exit(42)`, killing the native
Gateway while an external operation is gated, and an actual exec approval.
Every route first has a successful native receipt control. Worker process
identity, post-exit state, Gateway status and later independent tasks are retained.
Bare `gateway run` has no external systemd/container supervisor configured;
explicit restarts are counted as operator actions, not attributed to native
automatic supervision. Interrupted and neighboring sessions are separate data.

The confirmation case sets host exec `ask=always`, connects an authenticated,
paired native Control UI WebSocket client, waits for the matching public
`exec.approval.requested` event and resolves only the owned synthetic script with
`allow-once`. The independent file must be absent before review and the actual
approved process must then commit its receipt exactly once. This is an automated
owner acting as the reviewer, not a human time study. There is no shell-policy
bypass or secret-bearing command. Only owned fixture files/processes are changed.

The pinned public approval protocol is
`docs/gateway/protocol/rpc-devices-nodes-and-approvals.md` and
`packages/gateway-protocol/src/schema/exec-approvals.ts`; host policy follows
`docs/tools/exec-approvals.md` at OpenClaw source
`157d8c2bc3ea2fa183afdc11088e69690bf8e64e`. All model responses are scripted
and cost zero. Native calibration gates formal units. Existing hosted resource
bounds and mandatory owned-state cleanup apply. These data do not yet establish
an architectural explanation or behavior under an untested service manager.
