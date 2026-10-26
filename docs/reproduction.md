# Current evaluation reproduction

Current work targets OpenClaw only. The executable commands below validate and select plans or calculate token estimates; they do not execute product workloads. Historical two-product reconstruction instructions are preserved in the [V6 reproduction guide](history/v6-reproduction.md).

## Offline checks and selection

Use Python 3.11 or later from the repository root:

```sh
python3 tools/check_repository.py
python3 evaluation/tools/check_design.py
python3 -m unittest discover -s evaluation/tests -v
python3 evaluation/tools/suite.py list
python3 evaluation/tools/suite.py plan --dimension reliability
python3 evaluation/tools/suite.py plan --case EXT-08
python3 evaluation/tools/suite.py plan --dimension performance --phase real-model
```

No third-party Python packages, OpenClaw installation, network access or model credentials are needed. Plans always report execution disabled. There is no current `run` command; the V6 scripts are historical and must not be used as an implicit runner for these cases.

## Preparing a product run

For the initial architecture studies, start with `python3 evaluation/tools/architecture.py plan --wave 1` and the [architecture preregistration guide](../evaluation/architecture-studies.md). Its template/check commands declare the installed revision, contrasts, independent paired units, margins, budgets and hashed evidence. The checker verifies metadata/artifact consistency only and leaves product execution disabled.

Select cases from the [matrix](../evaluation/design/evaluation-matrix.json). Implement and validate their OpenClaw adapter and independent acceptance fixtures. Record the exact installed revision, effective config, plugin/hook revisions, model/provider, host topology, supported capabilities, task acceptance checks, fault triggers and independent event/effect ledger. Do not inherit historical pins or credentials.

Predeclare whole-run and per-case time, CPU, memory, disk/inode, process and connection limits, owned paths, cleanup behavior, repetition counts and required evidence. Keep one immutable dependency installation shared when compatible; writable copies are only for cases requiring mutation. Model-dependent task quality, prompt injection and billing require a separately defined real-usage budget. Validate fixtures before executing workloads; unknown capabilities remain unsupported or inconclusive rather than passes.

Record native trajectories and independent ledgers separately. Collect all attempted calls, failures, cancellations, resource samples, provider usage and charges; verify evidence before reporting product outcomes. Raw evidence and secrets stay outside version control. See the [measurement contract](../evaluation/measurement-contract.md).

## Token-cost calculation

```sh
python3 evaluation/tools/costs.py --usage /absolute/path/usage.json --pricing /absolute/path/pricing.json --accepted-tasks 1
```

Input formats and inclusive token semantics are specified in the [measurement contract](../evaluation/measurement-contract.md). Usage and prices must refer to the same provider and model. The calculator is offline and requires a dated price source; it ships no current model prices. It does not fetch invoices or measure usage by itself. Group requests by provider/model/price date and calculate each group separately before summing.

The result separates provider-reported amounts and calculated model-token estimates. Missing counters/rates remain unknown; cache and reasoning categories are subtracted from inclusive totals before pricing. Record non-token model fees, tool fees and infrastructure costs separately.
