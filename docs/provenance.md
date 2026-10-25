# Archive provenance

## File inventory

[`SOURCE_MANIFEST.json`](../SOURCE_MANIFEST.json) inventories every file under `v6/`. Each entry records its repository path, byte count, SHA-256 digest, and Git blob identifier. Historical source paths are retained when available. Files whose packaging documentation was updated also retain their original digest and source path.

The manifest covers archived evaluation materials. Repository governance files, documentation under `docs/`, CI configuration, and maintenance tools are reviewed through Git and are outside that archive inventory.

## Source claims and versions

[`v6/references/source-index.json`](../v6/references/source-index.json) maps architecture claims to the retained upstream source files and their SHA-256 digests. The copies are references for the historical experiment, not complete product checkouts.

[`v6/protocol/version_lock.json`](../v6/protocol/version_lock.json) distinguishes the main evaluation revisions from upgrade targets and preliminary version lookups. Those version records remain necessary to interpret V6; they are not earlier evaluation workspaces.

[`HISTORICAL_LAYOUT.json`](../HISTORICAL_LAYOUT.json) maps former machine paths to archived sources. These values document provenance and do not imply that the original machine layout exists on a new checkout.

## Preservation policy

Executable experiment code, frozen protocol data, task inputs, evaluator expectations, and third-party source retain their original contents. English repository documentation is maintained separately. The Windows bundle's translated README and packaging manifest are documentation updates; its controller and dependency pins remain unchanged.

Changes to experiment behavior or task inputs require a new documented experiment revision and new evidence. Updating a checksum alone does not validate a changed experiment.
