# Deployment, extension lifecycle and bounded sustained-load protocol

REL-09, EXT-01 and PERF-08 implement their twelve unchanged frozen scenarios.
The generic remaining-mechanisms workflow calibrates each native adapter first,
then executes all independent units only at the matching source hashes.

REL-09 keeps the native state and workspace while restarting with a changed
synthetic provider endpoint or credential. Independent endpoints enforce the
new grant. The old-endpoint-loss case actually closes that listening server;
the separate tool-receipt server stays available. The revoked-credential case
first proves that the old key receives 401. Continued task receipts and both
pre/post-restart transcript records are checked. This is provider binding and
session continuation, not an OAuth identity migration.

EXT-01 uses public native `plugins disable`, `reload --wait --json`, linked
`install --link`, and `uninstall --force` commands. It checks new calls after
disable, a retained in-flight call during replacement, native startup after
uninstall, and visible rejection/recovery after a replacement module throws.
An independent second plugin remains a positive availability control. Source
edits apply only to the owned reference plugin. No core patch is made. Linked
user source preservation after uninstall is intentional and reported.

The pinned reload contract is
`docs/cli/plugins/uninstall-and-update.md` at source
`157d8c2bc3ea2fa183afdc11088e69690bf8e64e`: retained calls finish while new
work waits for replacement; failed preparation reports whether publication
occurred. The experiment retains command output and independent owners/receipts.

PERF-08 predeclares a 60-second measured work window per scenario per unit,
plus native startup/warmup. Steady work reuses one session; session-creation
work uses fresh sessions; repeated connection faults actually close the first
provider completion socket for each new task before response bytes; drain adds
three seconds of idle observation. A closed loop waits one second after each
task, and records every offered request and independent effect. Task failures
remain visible. Interrupted durations are censored/incomplete.

Native process PSS, live descriptors/threads/processes, and owned disk/inodes
are measured across the window. Predeclared screening thresholds flag PSS
growth over 1 MiB/s or live-fd growth over 0.25/s. These diagnostic flags do not
prove a leak: session retention, caches and eventual reclamation require the
later unified analysis. Correctness is scored separately from resource slopes.
This finite-duration campaign does not establish multi-hour stability.

All providers are scripted local fixtures with zero paid calls. Hosted tmpfs,
memory, process/time and evidence bounds apply. Raw bounded artifacts expire
after 30 days; owned hosted installations, caches and state are always removed.
