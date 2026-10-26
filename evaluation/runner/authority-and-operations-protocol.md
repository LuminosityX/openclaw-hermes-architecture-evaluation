# Execution surfaces and operational diagnosis

SEC-01 exercises all five frozen execution surfaces using synthetic owned
canaries and native tool dispatch. Its deployment explicitly grants Gateway-host
exec (`security=full`, `ask=off`, sandbox off), trusts an enabled plugin and a
stdio MCP server, and restricts the native file tool with
`tools.fs.workspaceOnly=true`. The allowed workspace file is a positive control
for that restriction. In-process and plugin-launched child processes read only
owned outside-workspace canaries, and independent receipts retain actual process
identities. The child case is a reference plugin's own subprocess, not a claim
that the product advertises an isolated plugin host. Authority observed under an
explicit host trust grant is reported as such, not described as a sandbox escape.
Every path and network sink remains inside the outer disposable namespace.

OBS-05 uses a frozen automated runbook for four actual interventions: invalid
port configuration, corruption of the owned native transcript SQLite header,
an owned extension throwing on startup, and actual tmpfs ENOSPC. The SQLite
recovery copy is one owned synthetic database bounded to 4 MiB; no shared runtime
is copied. The storage intervention fills only owned temporary files, then removes
them. Native config validation, startup/HTTP attempts, console and structured
file logs provide diagnostics. The diagnosis function receives native text only,
before the separate truth category is scored. Ambiguous evidence remains unknown.
Recovery restores the corresponding owned configuration/database/plugin or frees
owned filler, then restarts and verifies a real independent task effect. Logical
interventions and privileges are retained. This is not a human operator study;
human active time is explicitly unknown.

Scripted tool plans never inject the expected canary into native tool results.
Acceptance requires the actual native tool return to contain the independent
owned canary or effect receipt. These deterministic tests measure execution and
diagnostic mechanisms, not model safety against prompt injection or model quality.

Native contracts are pinned to OpenClaw
`157d8c2bc3ea2fa183afdc11088e69690bf8e64e`, including public tool configuration,
MCP configuration, `docs/cli/doctor.md`, and `docs/gateway/logging.md`.
Heavy execution occurs only on disposable hosted workers; calibration must pass
before formal units. All owned runtime/cache/state is deleted, and raw bounded
artifacts expire after 30 days. Unified architectural interpretation stays deferred.

SEC-03 adds four native setup/path controls. The SSH cases first run a successful
native exec against an owned loopback SSH backend, then stop that actual backend
or point workspace initialization inside the read-only runtime bind mount. A
separate owned file detects any accidental Gateway-host fallback. The symlink
case uses a public before-tool hook to change an initially allowed link to an
owned outside-workspace canary immediately before native read dispatch, with
an independent event and link-target check. The allowed-file scenario remains
a positive control. Loopback SSH here tests native setup failure handling; it
does not establish isolation between independent hosts.
