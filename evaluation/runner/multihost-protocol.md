# Actual independent-host session placement

Each pair uses two independent GitHub-hosted Ubuntu VMs with distinct actual
kernel boot identities and exact pinned OpenClaw builds. A completes the
single-execution-host arm before B receives a remote endpoint. Native B opts
into full session hosting with one worker slot. A uses public sessions.dispatch
with the exact native cryptographic device ID, not system.run shell forwarding.
The dispatch's sealed worker-bundle hash, owner epoch, managed workspace and
native transcript are retained. The default model HTTP proxy and canonical state
remain on A; the native worker agent loop and local filesystem/process tools
execute on B. This distribution is reported explicitly.

A read-only helper is executed by native exec on each host. A separate root
observer joins the helper's namespace PID to an actual host kernel PID, owned
cgroup, command digest and namespace. It retains independent effect receipts.
Result reconciliation and native history are observed on A. Each VM separately
caps the controller/native runtime at 3 GiB memory, two CPU cores and 128 tasks;
adding B increases total resources. This is not equal-resource scaling, nor a
throughput improvement guarantee. Concurrent local and remote task outcomes
and task response latency are retained without claiming shared-clock precision.

The transport is a digest-pinned official cloudflared binary used only on GitHub
VMs. An ephemeral TLS/WSS hostname carries native authenticated traffic using a
run/unit-specific HMAC key from a dedicated campaign GitHub Secret. No real model
key is present. Native workloads run as UID 65534 with no capabilities, private
PID/mount namespaces and a read-only runtime. They cannot read host credentials.
Public rendezvous artifacts contain only hostname and public native device keys.

S04 drops IPv4 and IPv6 TLS output for only that native UID on disposable B,
requires a real existing native socket and positive kernel drop counters, then
restores the rules. S03 subsequently destroys B's entire native execution
namespace and its owned disposable disk state while an actual native tool is live. The root observer
survives to retain evidence; this is not physical VM power loss or a kernel
crash. Offline placement, failed/lost work and implicit replay are observed;
operator recovery is not silently granted or treated as an automatic retry.
Native state uses the actual GitHub VM disk, preserving the native 4 GiB free-space safety reserve check. Actual writes are monitored and bounded to 1 GiB per VM; no virtual filesystem capacity is forged.
All private native state and credentials are destroyed and endpoints closed
before bounded sanitized final evidence is uploaded. Real independent-host
calibration must pass fixture validation before the six formal pairs can start.
