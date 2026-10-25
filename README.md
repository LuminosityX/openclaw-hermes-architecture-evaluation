# OpenClaw and Hermes Architecture Evaluation

**Branch status:** This research branch adds the [V7 evaluation design](v7/README.md). The `main` branch preserves the V6 experiment archive. V7 product experiments have not been executed.

V6 experiment harnesses, task fixtures, scoring rules, and source references for evaluating the architecture of OpenClaw and Hermes.

This repository is a **source archive**. Repository checks run offline with Python 3.11 or later. Repeating the product experiments requires reconstructing the pinned runtimes; cloning this repository does not install or start either product.

## Evaluated versions

| Product | Main evaluation version | Source commit |
| --- | --- | --- |
| OpenClaw | `2026.10.6` | `fe06181dc5ecc01cf8904abbfc26925925efefbc` |
| Hermes | `0.22.5` | `bf0203a794a07aac3ff764972ab9087baa4e4f4e` |

These are historical experiment pins, not recommendations for current deployments. Upgrade cases use the additional versions recorded in [the version lock](v6/protocol/version_lock.json).

## Quick start

```sh
git clone https://github.com/zyw02/openclaw-hermes-architecture-evaluation.git
cd openclaw-hermes-architecture-evaluation
python3 tools/check_repository.py
```

The check validates archive hashes, source references, Windows bundle integrity, Python syntax, JSON structure, documentation links, and the existing scorer self-tests. It does not install dependencies, contact model APIs, start containers, or run product experiments.

## Repository layout

| Path | Contents |
| --- | --- |
| [`v6/scripts/`](v6/scripts/) | Experiment controllers, analysis scripts, and audit utilities |
| [`v6/fixtures/`](v6/fixtures/) | Public task inputs and pinned project fixtures |
| [`v6/private-fixtures/`](v6/private-fixtures/) | Synthetic evaluator inputs and acceptance oracles; no service credentials |
| [`v6/protocol/`](v6/protocol/) | Frozen protocol, observation template, scorer, and version lock |
| [`v6/support/`](v6/support/) | Shared scripts required by V6 |
| [`v6/dependencies/`](v6/dependencies/) | Archived product dependency declarations and lock files |
| [`v6/references/`](v6/references/) | Referenced upstream source files, claim index, and licenses |
| [`v6/patches/`](v6/patches/) | Controlled counterfactual patch and source revision records |
| [`v6/windows-native-bundle/`](v6/windows-native-bundle/README.md) | Separate native Windows verification bundle |
| [`docs/`](docs/) | Methodology, reproduction, and provenance documentation |
| [`tools/`](tools/) | Offline repository validation and manifest maintenance |

Earlier experiment versions and duplicate controller snapshots are excluded from the current source tree. Historical upgrade targets and shared support scripts remain where V6 requires them.

## Scope and reproduction

The evaluation covers eleven architecture dimensions, from recovery and isolation to extensibility and compatibility. See [methodology](docs/methodology.md) for the scope and [reproduction](docs/reproduction.md) for the distinction between offline validation and product execution.

Raw logs, state databases, result records, installed applications, package caches, and real credentials are not distributed here. They are maintained separately from the source archive. The Windows bundle was prepared on Linux; its presence does not establish successful native Windows execution.

Repository documentation is written in English. Frozen protocol fields, synthetic task prompts, multilingual test strings, and quoted upstream source are preserved in their original language because changing them would alter experiment inputs or provenance.

## Contributing and licensing

See [CONTRIBUTING.md](CONTRIBUTING.md) for archive-preserving changes and [SECURITY.md](SECURITY.md) for private reporting. The original evaluation materials remain all rights reserved under [LICENSE](LICENSE). Included third-party materials retain their own licenses, listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
