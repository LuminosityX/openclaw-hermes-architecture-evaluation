# Native full-backup consistency under active work

REL-10 runs native `backup create --verify --json` for the four frozen scenarios:
idle state, ongoing native session writes, queued native work, and interruption
during actual native backup staging/publication. It never copies a live database
file as a substitute for the product backup API.

An acknowledged native task is completed before every backup. Independent archive
inspection then opens bounded SQLite payloads read-only, runs `quick_check`, and
looks for the acknowledged transcript marker. The idle case also exercises native
restore to a fresh staging directory, without claiming relocation/activation.
The concurrent writer runs real sessions until backup returns. Queued work uses
one native active slot and an independently gated external effect; public native
history/custody must show the queued input before capture and its provider request
must not yet have started. All offered work is reconciled after draining.

For interruption, a previous verified generation is retained, and an owned 2 MiB
workspace payload lengthens publication enough to observe real backup staging.
The native process group is killed only after a new backup staging/work path is
observed. A missed intervention remains a harness error. The prior generation is
hash-checked and natively reverified. A surviving new archive is classified
explicitly: a partial artifact must be rejected by native verification, while a
complete published artifact is independently checked even if CLI confirmation
was interrupted. The public contract never promises that every interrupted CLI
leaves an invalid archive. Every scenario restores its baseline into fresh native
staging. Residual owned staging bytes are recorded before namespace
cleanup. No shared installation or cache is copied.

The consistency promise follows the pinned `docs/cli/backup.md` and
`docs/install/backups.md`: config is captured before databases; SQLite snapshots
are consistent per database. This experiment never assumes one atomic snapshot
across config and every database. Expanded inspection is capped at 16 MiB,
individual synthetic databases at 4 MiB, and all state remains in the existing
bounded hosted tmpfs. Raw archive payloads are never downloaded to the local
workspace or uploaded as evidence; only metadata, hashes and independent checks
are retained. Zero real provider calls; calibration precedes formal units.

Native verification reserves 256 MiB of free scratch capacity. The first
calibration (40310339841) correctly refused verification in the generic 64 MiB
tmpfs; this is an environment precondition, not a formal product failure. REL-10
therefore uses a separate hosted-only 384 MiB tmpfs ceiling with the same 3 GiB
cgroup and zero swap. Capacity is virtual tmpfs, not a local disk allocation;
actual state/payload bytes remain bounded and owned. Local execution and all
other families retain their original small tmpfs profiles. The one-time capacity
guard is kept separate from product hardware measurements.
