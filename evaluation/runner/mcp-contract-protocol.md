# MCP transport, generation and cancellation experiments

REL-13 and EXT-05 cover eight unchanged frozen scenarios. Tiny owned peers
implement actual stdio, Streamable HTTP JSON responses and legacy HTTP/SSE streams.
Every case first requires a real native MCP tool/receipt control on that transport.
There are no external network destinations or private OpenClaw imports.

The HTTP peer records initialization generations, RPC IDs, actual arguments,
committed effects, cancellation notifications and attempted responses. Expiry
actually invalidates a server session and returns 404. Reconnection during a call
actually closes its HTTP socket after an independent effect commit. The pinned
contract reports the failed call without replay, then retires expired connections
for later discovery. Both the failed call and a later discovery/task are retained;
an already committed external effect is never treated as absent.

Cancellation holds an actual remote call behind an independent gate until the
native sessions.abort response returns. S03's peer cooperatively honors a matched
MCP cancellation notification before effect commit; S04 commits before cancellation
and deliberately attempts a late return. Native active-status acknowledgment,
request liveness, RPC/gate timing, task completion and independent effects remain
separate checks. Nullable aborted run IDs follow the public status contract.

Content probes exercise text, structured-only fields, embedded resource URI/text,
Unicode arguments/results and a predeclared full 32 KiB result in the native
model-facing tool return. These are transport/content fixtures, not a claim about
all MCP apps, arbitrary result sizes, resource fetching, or model safety. Actual
native return bytes are retained in bounded hosted summaries; local records keep
assertions and provenance rather than large payloads. All provider calls are
scripted and incur zero model charges.

Pinned OpenClaw contracts: `docs/cli/mcp/transports.md` and
`src/config/zod-schema.mcp-server.ts` at
`157d8c2bc3ea2fa183afdc11088e69690bf8e64e`. Native calibration precedes every
formal batch; fixture failures remain incomplete, not product failures. Existing
hosted runtime, memory/time/storage limits and mandatory cleanup apply.
