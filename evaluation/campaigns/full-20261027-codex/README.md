# Formal Codex campaign progress

The active frozen plan has **3/257 scenarios completed** with **9 independent
observations** (run [40619641576](https://github.com/LuminosityX/openclaw-hermes-architecture-evaluation/actions/runs/40619641576)).
3 scenarios pass, 0 retain failure observations, 254 remain incomplete. Only
accepted formal hosted records count; local adapter calibration stays
development evidence and is rejected by the retention tool.

Codex is pinned to `0.164.0`, source `6aaac694803004a63c6f393d153c96d22521a6b9`
(rust-v0.164.0 release-tag binding; see [codex-target-pin.json](../../design/codex-target-pin.json)).
Each scenario completes its prescribed three (or six) independent units on
disposable GitHub-hosted runners. Adapters land family by family; the
[campaign workflow](../../../.github/workflows/codex-campaign.yml) executes
every calibrated family in its matrix.

| Family | Completed scenarios | Independent observations | Hosted runs |
| --- | ---: | ---: | --- |
| REL-01 Admission and persistence boundaries | 3 | 9 | [40619641576](https://github.com/LuminosityX/openclaw-hermes-architecture-evaluation/actions/runs/40619641576) |

Retained-failure observations: none yet.

## First mechanism observation (REL-01, three units each)

- A prompt held by the client (stdin gate) leaves no rollout record and no
  completion: a merely received request is distinguishable from an
  acknowledged one.
- At the model-request gate the prompt is already durably appended to the
  rollout exactly once; killing the process there leaves no completion marker.
  `codex exec resume --last` continues the thread, preserves the input exactly
  once and completes the work exactly once.
- After an acknowledged completion, a crash of the dependent resume turn does
  not re-execute the acknowledged turn (its provider response appears exactly
  once in the usage records) and the dependent turn completes after a second
  resume.

These are deterministic-fixture mechanism observations for the declared
boundaries only; they do not measure model quality or general task capability.
