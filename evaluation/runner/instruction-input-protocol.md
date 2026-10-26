# Owned AGENTS and Skill input compatibility

EXT-06 implements its four frozen scenarios using actual native provider inputs
and native file tool returns. Root AGENTS instructions are placed in the owned
workspace before startup. A nested AGENTS file is explicitly read through the
native file tool; automatic nested injection is measured separately and is not
assumed by the oracle. Extra skills use the documented `skills.load.extraDirs`
root. Their actual name/description must reach the native skill roster, and the
body is then read through the public tool. A relative supporting file is read in
the same native session after reading the skill. The scripted controller resolves
the documented base directory; it does not claim automatic resource execution.

The conflict case compares a same-named workspace skill and extra-directory skill,
plus a missing-binary gate in current `metadata.openclaw` and an intentionally
obsolete `metadata.clawdbot` gate. The public pinned contract gives workspace skills
higher precedence and no longer reads pre-July-2026 clawdbot gating. All sources
are tiny owned synthetic fixtures. Reads to the configured extra skill directory
are explicitly granted by this deployment; this is not an isolation bypass test.

The provider fixture observes actual native system/messages. Retained evidence
contains context hashes, marker-presence facts, source hashes and actual tool
returns, rather than copying whole prompts into the repository. This tests native
discovery, precedence and content transport; it does not measure model obedience
or behavioral equivalence with another framework. Zero real provider calls.

Contracts at OpenClaw source `157d8c2bc3ea2fa183afdc11088e69690bf8e64e`:
`docs/concepts/agent-workspace.md`, `docs/tools/skills.md`, and
`docs/tools/creating-skills.md`. Whole-family native calibration precedes formal
units. Heavy execution, dependencies and state stay on disposable hosted runners;
the existing cleanup and evidence bounds apply.
