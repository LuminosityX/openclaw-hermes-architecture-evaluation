# Bounded local pilot runner

This is an actual OpenClaw Gateway adapter for the three first-wave exploratory studies, using a deterministic local provider and real native tool execution. It does not implement the complete 60-family suite or validate real-model task quality. The plan-selection tools remain offline; this runner requires an explicit runtime and output path.

The [source-directed followups](../source-investigations.md) add `SRC-01` through `SRC-04`: discovery strategy/schema footprint, wait-dependent admission with main-thread diagnostics, exception/termination/UID boundaries, and relative versus explicit SSH paths. Completed arms emit small checkpoints so an outer failure can retain evidence. A valid measurement can contain a product counterexample; source followups keep control validity separate from task-contract and excluded-operation outcomes.

By default the supplied installation must match the exact [current stable campaign](../current-version.md) version and release commit. A mismatched historical runtime requires `--allow-historical-bootstrap` and produces a bootstrap-only label. Use the hosted workflow when the new release would require another local installation.

## Storage and host limits

- Reuse an already-built OpenClaw `node_modules` tree and compatible Node binary through read-only mounts. No clone, dependency install, package update, Docker image pull or dependency copy is performed.
- All mutable runtime state, workspaces, SQLite/WAL files, logs, SSH host/client keys and caches live inside a kernel-sized tmpfs: 64 MiB by default, configurable only from 16 to 128 MiB. A capacity probe must receive kernel `ENOSPC` before any Gateway starts; its probe files are deleted immediately.
- An owned cgroup caps the complete experiment at 1 GiB memory by default, zero swap, 128 processes/threads and two CPU cores of scheduling quota. Core dumps are disabled and individual files are capped at 16 MiB. The default whole-run timeout is 600 seconds. These limits are experiment conditions, not measured product requirements.
- The explicit `--hosted-profile` permits a selected memory ceiling up to 4 GiB for disposable hosted workers; the current stable workflow selects 3 GiB. The local profile's default and 1536 MiB upper bound remain unchanged. The report records which profile and exact limits were used.
- Only one host pilot may run at a time, enforced by an abstract Unix-socket lock with no lock file. Unrelated host workloads can still contend; no dedicated physical CPU or host-memory reservation is claimed.
- No host directory is mounted writable. A separate network namespace contains only loopback endpoints. Existing gateways, personal state, user credentials on disk, unrelated processes and existing dependency stores are not modified.
- On exit, the PID namespace and tmpfs disappear; the wrapper kills remaining owned cgroup processes and removes its cgroup. Only one JSON report of at most 1 MiB is persisted to a new explicitly selected output directory; existing output is never overwritten. Reports contain synthetic data only. Raw databases, logs and private SSH keys are not retained or archived.

The optional owned SSH fixture needs `CAP_SETUID`, `CAP_SETGID` and `CAP_SYS_CHROOT` for OpenSSH privilege separation inside the isolated PID/filesystem/network environment. It does not use a user namespace; other capabilities remain dropped. The default non-SSH profile unshares all supported namespaces and drops all capabilities. Neither profile is presented as a tested OpenClaw malicious-code isolation boundary.

## Requirements and command

Linux, cgroup v2 with writable delegated control under `/sys/fs/cgroup/system.slice`, Bubblewrap, Python 3.11+, an existing compatible Node binary and built OpenClaw installation. The optional SSH profile also uses existing `ssh`, `sshd` and `ssh-keygen`; it does not install them or contact a remote machine. Missing prerequisites fail rather than triggering downloads or changing the host's installed services.

```sh
python3 evaluation/tools/run_local.py \
  --runtime-modules /absolute/path/to/existing/node_modules \
  --node /absolute/path/to/compatible/node \
  --output /absolute/path/to/new/pilot-output \
  --study first-wave --ssh-backend --blocks 2
```

`--study` can select `smoke`, `ARC-01`, `ARC-02`, `ARC-03`, or `first-wave`. Keep runtime and controller files unchanged during a run; the report records their build identity and controller SHA-256 hashes. `--blocks` accepts 1 through 4 paired blocks, intended for pilots rather than confirmatory statistics. The first wave runs sequentially with alternating arm order and fresh Gateway state. It can take a few minutes because every arm starts a real Gateway.

Without `--ssh-backend`, ARC-03 probes the default backend. If Docker is absent, it records the native missing-backend failure and does not claim the scope comparison was measured. It does not provision Docker even if that would make the comparison possible.

## What the pilots observe

ARC-01 compares native cross-session concurrency caps of one and four for eight independent sessions. A registered native plugin calls an independently logged local effect server. Accepted responses, exact effect counts, actual overlap and text receipt persistence in native SQLite are cross-checked. A warmup precedes measured batches. Latency is end-to-end; queue wait and first-output delay are not separately attributed. Process-tree CPU/PSS/RSS samples include startup and warmup, and sampled RSS sums are not physical memory.

The deterministic provider follows advertised tools. If the release exposes catalog controls, it searches the exact target, reads the returned catalog ID, describes it, then invokes that ID through the native call control. It leaves native Tool Search defaults enabled. MCP catalog JSON may have an external-content warning; parsing extracts only matching catalog metadata, while target arguments remain fixed synthetic fixture inputs. Completion still requires the real receipt and independent ledger. The published [2026.10.7 protocol](https://github.com/openclaw/openclaw/blob/v2026.10.7/docs/tools/tool-search.md) is the versioned reference; live documentation may describe later control names.

ARC-02 compares the same receipt operation through a native plugin and a real stdio MCP server. Each route has a successful control before a controlled 600 ms CPU block and an `exit(42)` fault. Neighbor response latency, actual fault markers, Gateway survival and post-fault independent requests expose the failure domain. It is a route comparison with transport/interface differences, not a pure causal cost of process isolation. Trusted synthetic code is not a hostile-plugin security test.

With the SSH fixture, ARC-03 uses OpenClaw's native SSH sandbox backend against an owned loopback OpenSSH server. Agent and session scope use identical target, backend, grants and workspace access. One session writes a synthetic canary, a second session checks its current directory, then the first session revisits its state. The runner records native command results, independently visible remote paths, latency and resources. This measures workspace ownership and reuse. The same SSH OS identity can explicitly traverse sibling paths, so separate working directories do not establish hostile-tenant OS isolation. The result does not describe Docker performance or a real multi-host deployment.

The reports preserve observations and inference limits rather than generating a product grade. Small pilot samples cannot establish general latency quantiles, equivalence, vulnerability rates or the optimality of a design. Hardware counters not collected, full trace coverage, real problem-solving ability, actual token charges and most security probes remain unmeasured.
