Integration cases for rows 02, 09, 13, 18, 21 and 22
=================================================
Measured pinned source owners, not a replacement implementation. All framework
code stayed unchanged. Local scripted model fixes the execution plan; no paid
model calls. The scope/limitations in each results/extended-row-XX.json are part
of the result and must accompany any graph.

Environment: root RUNBOOK, Node 24 + tsx, Hermes venv, ssh/sshd, native OpenClaw
process-owner build, Playwright Chromium cache. Hermes API adapter additionally
requires aiohttp (installed in envs/hermes). Existing configured model secrets
are not required. Isolated fixtures listen only on loopback.

Run from benchmark root. Keep the source working directory for Node scripts so
tsx resolves the pinned workspace packages. Use:
  NODE=envs/openclaw-toolchain/node_modules/node/bin/node
  TSX=envs/openclaw-toolchain/node_modules/tsx/dist/loader.mjs
  PY=envs/hermes/bin/python
Use absolute paths when launching Node from sources/openclaw.

1. python3 scripts/integration_ssh_fixture.py
   Starts two dedicated SSH services and creates fresh TEST SSH credentials
   under runtime/extended-integration/ssh. Never package the private keys.
2. Start python3 scripts/integration_model.py (port 38691),
   python3 scripts/integration_browser_fixture.py (HTTP 40310, CDP 40311),
   Node + tsx scripts/integration_openclaw_gateway.mjs (native gateway 40321),
   and $PY scripts/integration_hermes_gateway.py (native adapter 40322).
   They are foreground services. Wait for both HTTP /health routes to answer.
   The gateway config disables compact tool search to directly advertise the
   native delegation tool; the earlier preflight without that setting is kept
   in raw/extended-integration/*-preflight.json.
3. Execute each native probe once, writing raw evidence:
   integration_openclaw_ssh.mjs and integration_hermes_ssh.py
   integration_openclaw_mcp.mjs and integration_hermes_mcp.py
   integration_openclaw_browser.mjs and integration_hermes_browser.py
   Use Node+tsx / Hermes Python respectively.
4. python3 scripts/integration_gateway_cases.py openclaw
   python3 scripts/integration_gateway_cases.py hermes
   python3 scripts/integration_gateway_cases.py openclaw --delegation
   python3 scripts/integration_gateway_cases.py hermes --delegation
   Each command defaults to 10 actual cases and a unique run tag. Keep one
   child at a time. No concurrency/latency claim is made.
5. python3 scripts/integration_summarize.py
   python3 scripts/integration_audit.py
   The audit additionally checks native child completion, not just accepted
   spawn requests or generic terminal exit codes.
6. Stop only the fixture PIDs you launched. OpenClaw catches SIGTERM and joins
   native worker cleanup. Both SSH fixture PIDs are in its endpoints.json;
   Chromium PID in browser/chrome.pid. Never stop unrelated user gateways.

Observations: each row is 10/10 for each framework in its limited functional
scope. Equal bars show equal fixture pass rates; they are not evidence of
identical architecture, production reliability or broad feature equivalence.
02/18: co-located SSH endpoint simulation, not two physical cloud machines.
09: one native child and one terminal call per parent; fixed orchestration.
13: fresh stdio MCP sessions and payload/schema round trips only.
21: native OpenAI-compatible HTTP entrance -> tool -> HTTP reply only.
22: native browser owners with fixed DOM actions and independent form-server
submission checks; no model planning, screen perception or desktop automation.
