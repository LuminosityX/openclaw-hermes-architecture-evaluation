# Current stable campaign

Use the latest published stable OpenClaw release at the beginning of a campaign, then freeze its exact version, tag commit and npm package integrity for that campaign. Do not use a moving `main` checkout or silently combine versions. A subsequent stable release starts a separately labeled campaign; a nightly build is a separate regression subject.

On 2026-10-26, GitHub's latest non-prerelease release and npm's `latest` both resolve to [2026.10.7](https://github.com/openclaw/openclaw/releases/tag/v2026.10.7), commit `157d8c2bc3ea2fa183afdc11088e69690bf8e64e`. Its published Node requirement is `>=24.22.1 <25 || >=26.12.1`; this campaign pins Node `24.22.1`. The [matrix target](design/evaluation-matrix.json) owns these values, including the registry tarball's SHA-512 integrity and resolution timestamp.

```sh
python3 evaluation/tools/target.py check-current
```

This command consults official public metadata and fails if the frozen target is stale or registry/release sources disagree. `target.py refresh` explicitly updates the pin before a new campaign; review that change and its runtime requirements rather than letting an in-flight experiment change versions.

The active [full campaign](full-campaign.md) requires completing all experiments before unified architecture interpretation. The workflows below include historical exploratory pilots; their completion is not full-suite completion. New native adapter and task calibration also use disposable hosted runners and retain only bounded synthetic evidence.

## Avoid another local installation

The manually dispatched `Current stable OpenClaw pilot` GitHub workflow installs the exact published version and compatible Node on a fresh GitHub-hosted Ubuntu runner. It checks installed package/build versions, release commit and npm lock integrity before invoking the bounded three-study pilot. Dependencies and npm caches stay on that temporary machine and are removed after the job. No runtime cache is uploaded or reused by the workflow.

Only compact evidence is uploaded: installation identity, a minified dependency lock, execution metadata and the pilot's bounded JSON report. Their total must be at most 2 MiB; artifacts expire after three days. Local retrieval is limited to those small files. The runtime and cache are not downloaded back to the user's machine.

Runtime state still uses the 64 MiB tmpfs and zero-swap experiment cgroup. Hosted runs use an explicit `--hosted-profile` with 3072 MiB experiment memory, recorded in the report, and are not a resource-matched comparison with the historical 1 GiB local bootstrap. A 1536 MiB current-release attempt was terminated by its cgroup OOM policy before producing product observations; it is retained as a resource-budget failure, not silently counted as a completed experiment. The hosted installation/cache check is capped at 4 GiB after installation; that is temporary cloud disk, not local disk or a claim about the product's minimum footprint.

## Keep bootstrap evidence separate

The retained [2026.9.2 execution](evidence/README.md) is historical harness validation. Its observations cannot establish the strengths, defects or performance of the current release. `run_local.py` rejects builds whose version/commit differ from the current campaign. `--allow-historical-bootstrap` is an explicit opt-in for old-build harness work and labels the report `historical-bootstrap-only`; it never promotes that build to current-release evidence.

The [current stable evidence](evidence/current-stable-20261026/README.md) now contains valid two-block observations for all three first-wave studies, with exact source-job selection and setup-failure history. The full case inventory remains planned. Repository CI validates these tools without installing OpenClaw or running paid models; the explicitly dispatched hosted workflow performs the native pilots.
