# Native migration and snapshot rollback protocol

The current target remains 2026.10.7. A separately integrity-pinned real
2026.10.4 installation generates schema 24; the current native Doctor advances
that data to schema 25. Adjacent 2026.10.6 has the same schema as the target and
cannot establish a schema-migration intervention.

Each fresh unit creates acknowledged native history, a native verified backup,
and an independently inspected baseline of the backup's complete transcript
columns and record identities. No schema, timestamp or transcript row is edited.
The Linux x86-64 tracer follows only owned native descendants, inspecting writes
to the exact owned agent database WAL. It selects a noncommit page-one frame
containing the actual higher schema cookie and user_version 25. S01 kills before
that page reaches the WAL; S02 kills after its actual successful pwrite64 but
before the commit marker. These are persistence boundaries, not claims about
when in-memory SQL DDL begins. A missing real boundary invalidates calibration.
The independently read committed database must remain version 24 at either cut.
A direct old-binary reopen is recorded separately: an explicit native maintenance
refusal is an observed safe fence, not a harness exception or proof of automatic
recovery. Recovery is independently required through the documented snapshot
rollback below. S03 commits actual migration, then kills a new native Gateway before readiness.
S04 uses an identical explicitly version-constrained owned extension, first
proven on the historical core; registration on the new core is observed along
with unrelated native work. This does not generalize to all third-party plugins.

Rollback stops owned native processes, runs native backup restore from a clean
operator configuration, activates complete state/config/workspace assets at their
original paths, and starts the historical binary. It verifies all archived
transcript columns and IDs before any continuation and then performs new native
MCP work in the retained session. A binary-only downgrade is observed separately.
The evaluator alone holds ptrace capability; the native CLI and Gateway drop all
capabilities. Runtime installs and raw state exist only on disposable GitHub VMs.
