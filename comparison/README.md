# Cross-product evaluation

This workspace compares Codex, DeepSeek Harness (DSH), and OpenClaw at the platform and harness layers. The [execution plan](plan.md) describes scope and priorities; [first-wave protocols](first-wave-protocol.md) define concrete interventions, observations, and limits. The [progress ledger](progress.json) records per-product work items. The [frozen OpenClaw campaign](../evaluation/README.md) and [V6 archive](../v6/) preserve their original evidence and do not count as a completed three-product comparison.

## Progress maintenance

Update each cell's status, evidence paths, and notes in `progress.json`, then run `python3 comparison/dashboard.py` and commit the ledger and generated README. `python3 comparison/dashboard.py --check` detects drift. GitHub Actions shows live job steps. When session calibration finishes, its aggregation job writes the latest run link and outcome to the research branch and regenerates the README. Other experiment states are maintained by their owners; CI does not infer formal completion from a calibration pass. Cells represent work items, not sample counts or success rates.

Statuses are `planned`, `in_progress`, `blocked`, `done`, and `not_applicable`. The last two require an evidence file in the repository. Historical evidence cannot complete a new experiment when its protocol differs. A valid experiment with failed acceptance can be `done`; its failure must remain visible in the evidence.
