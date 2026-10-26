# Native state, workspace and UID relocation

REL-06 implements state-path-only, workspace-path-only, UID-only and combined
relocation. A native task first commits a transcript and an owned reference
extension counter. A disabled native cron job scheduled one day ahead supplies a real
scheduled-state identity without running any model call. The Gateway stops before
the owned state/workspace trees move. Configuration paths are explicitly rebased,
and native `doctor --fix --non-interactive` runs as the intended new owner before
the new Gateway starts, following the pinned migration guide.

UID cases actually launch the native Gateway after setgroups/setgid/setuid to
1001. They do not simulate identity migration with a path alias. Only the owned
case tree and scratch home/cache/tmp are re-owned; symlinks are never followed.
The outer controller gains CAP_CHOWN and CAP_KILL only for this hosted family so
it can repair owned-file ownership and stop the new-UID native child inside its
PID namespace. No DAC-override or ptrace authority
is added, and the immutable shared runtime stays read-only. Nonzero UID native
children lose the controller's capabilities. This profile is unavailable to local
execution and is not a claim of UID-namespace or hostile-tenant isolation.

Hosted toolcache executable permissions can be private to the setup user. This
family makes one byte-identical, SHA-checked Node executable clone with mode 0755
inside its owned hosted runtime directory and explicitly traversable namespace
parents. The OpenClaw installation is still shared read-only. The single clone is
recorded, included in the same 4 GiB hosted installation/cache ceiling and deleted
with the job. No executable or permission change occurs on the local machine.

Public native RPC checks the same session identity/history and cron job identity.
Independent plugin receipts report the actual native UID and counter continuation.
Native read and exec/pwd check migrated workspace content and execution location.
PSS after UID drop is unavailable because the controller lacks ptrace authority;
it is null with a reason, not reported as zero. Existing owned cgroup accounting
still describes the whole run.

These are same-host controlled relocations. Cross-OS and independent-host migration
are separate experiments. All credentials, cron payloads and workspace artifacts
are synthetic. No runtime copy, real model call or local installation occurs.
Contracts are pinned to `docs/install/migrating.md` and
`packages/gateway-protocol/src/schema/cron.ts` at OpenClaw
`157d8c2bc3ea2fa183afdc11088e69690bf8e64e`. Whole-family native calibration
precedes formal units, with the existing memory/time/storage/cleanup bounds.
