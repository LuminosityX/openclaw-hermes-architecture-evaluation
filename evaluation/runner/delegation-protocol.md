# Native child interruption and owner expiry

REL-03 uses actual sessions_spawn children and an independent MCP HTTP service.
The service can retain a live operation or its committed effect across native
Gateway/child interruption. Late replies and implicit replays are counted
separately from an explicit operator retry. Successful captures require a native
live child before intervention and readable native history afterward.

S02 cancels only the child, retaining the same Gateway and child session. The
operator continues it through documented sessions.send, with a fresh idempotency
key. The original child session ID, new operator message, actual second MCP
invocation and receipt must be observed. Generic HTTP completions deliberately
reject internal session namespaces and cannot establish a child-resume failure.
That original invalid probe remains quarantined with its unchanged raw evidence.

S03 freezes only the actual native execution cgroup while the evaluator and MCP
service remain live, observes the native five-minute lease expiry without editing
state, probes a second coordinator, then kills the old physical owner and probes
recovery. Logical lease expiry and physical custody are distinct observations.
No native core is patched, and all execution/state remains on disposable GitHub VMs.
