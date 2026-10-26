# Reproduction guide

## Offline validation

Requirements: Git and Python 3.11 or later. No third-party Python packages are required for repository validation.

From the repository root, run:

```sh
python3 tools/check_repository.py
```

To run only the existing scorer self-tests:

```sh
python3 v6/protocol/score_protocol.py --selftest
```

To score an observation file that already satisfies the frozen protocol:

```sh
python3 v6/protocol/score_protocol.py --observations /absolute/path/to/observations.json --output /absolute/path/to/scores.json
```

The empty observation template is not a completed evaluation and must not be presented as one.

## Reconstructing a Linux experiment environment

The archived controllers are historical experiment code, not a portable installer. Before running them:

1. Read the [protocol](../../v6/protocol/protocol_v1.json) and the specific controller to identify its inputs and required services.
2. Reconstruct the application revisions in [version_lock.json](../../v6/protocol/version_lock.json). The Hermes dependency files are upstream snapshots, not installation metadata for this repository.
3. Resolve the historical paths using [HISTORICAL_LAYOUT.json](../../HISTORICAL_LAYOUT.json). Apply the most specific mapping first. The original `private/` input directory is archived as `v6/private-fixtures/`.
4. Rebuild omitted runtimes and tools. Depending on the controller, these include Node.js, a Hermes-managed Python environment, PyYAML for the host-side YAML reader, Bubblewrap, cgroup v2 support, and a dedicated Docker daemon. Binary paths, sockets, caches, and application installation stores are not included in the source mappings.
5. Supply fresh credentials and an explicit budget for real-model runs. Historical authorization records and controller defaults do not define a budget for a new run.
6. Execute the required preflight checks in a dedicated experiment environment before collecting paired measurements.

There is no single supported command that reconstructs all of these services. Individual `run_*.py`, `prepare_*.py`, and cleanup scripts can create, modify, or delete experiment state; they are not part of the offline validation command.

## Data and storage

The source archive includes synthetic public inputs and evaluator-only expected outputs. The `private-fixtures` name describes evaluator visibility; those files are not a credential store.

Raw logs, state databases, final results, and their compressed evidence archive are stored separately. Do not recreate historical result claims from source inspection alone. Match source versions, observation identifiers, and manifests to the retained evidence when auditing a result.

For a new run, keep immutable application dependencies shared where the experiment permits it. Create writable dependency copies only for cases that intentionally test installation, upgrades, or storage faults. Keep dependency installations and caches out of version control, and remove the dedicated run environment after preserving the required evidence.

## Windows bundle

Use the [Windows-specific instructions](../../v6/windows-native-bundle/README.md). This is a separate CLI verification bundle, not a Linux-to-Windows full-state migration test. Native execution is not performed by this repository's CI.
