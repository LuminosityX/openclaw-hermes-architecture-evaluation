import fs from 'node:fs';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import { pathToFileURL } from 'node:url';

const root = path.resolve(import.meta.dirname, '..');
const source = path.join(root, 'sources/openclaw');
const nativeOwner = path.join(source, 'dist/process/supervisor/service-child-group-anchor.js');
if (fs.existsSync(nativeOwner)) {
  const { registerSealedRuntimeProcessEntrypoint } = await import(pathToFileURL(path.join(source, 'src/infra/runtime-process-url.ts')));
  registerSealedRuntimeProcessEntrypoint('serviceChildGroupAnchor', pathToFileURL(nativeOwner));
}
// This is the production agent-exec command owner, called directly without CLI parsing.
const { agentExecCommand } = await import(pathToFileURL(path.join(source, 'src/commands/agent-exec.ts')));
const mode = process.argv[2] ?? 'smoke';
const tools = Number(process.argv[3] ?? 4);
const delay = Number(process.argv[4] ?? 200);
const surface = process.argv[5] ?? 'terminal';
let configPath = process.env.BENCH_CONFIG_PATH ?? path.join(root, 'envs/openclaw-bench-config.json');
const modelId = process.env.BENCH_MODEL ?? 'bench/bench-scripted';
const timeoutSeconds = process.env.BENCH_TIMEOUT ?? '60';
const suppliedPrompt = process.env.BENCH_PROMPT_FILE ? fs.readFileSync(process.env.BENCH_PROMPT_FILE, 'utf8') : undefined;
if (surface === 'mcp') {
  const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  config.mcp = { servers: { bench: { command: '/usr/bin/python3', args: [path.join(root, 'scripts/mcp_fixture.py')], transport: 'stdio', enabled: true, supportsParallelToolCalls: true, connectionTimeoutMs: 5000, requestTimeoutMs: 5000 } } };
  config.tools.alsoAllow = ['bench__bench_delay'];
  // Match the common MCP benchmark's directly advertised single-tool surface.
  config.tools.toolSearch = false;
  configPath = path.join(root, 'envs/openclaw-bench-mcp-config.json');
  fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
}
const workspace = process.env.BENCH_WORKSPACE ?? path.join(root, 'fixtures/agent-workspace');
const state = process.env.BENCH_STATE_DIR ?? path.join(root, 'envs/openclaw-agent-state');
fs.mkdirSync(workspace, { recursive: true });
fs.mkdirSync(state, { recursive: true });
const samples = [];
const sampleCount = mode === 'smoke' ? 1 : Number(process.env.BENCH_SAMPLES ?? 30);
const warmupCount = mode === 'smoke' ? 0 : Number(process.env.BENCH_WARMUPS ?? 5);
if (!Number.isSafeInteger(sampleCount) || sampleCount < 1 || !Number.isSafeInteger(warmupCount) || warmupCount < 0) throw new Error('Invalid benchmark sample/warmup count');
for (let index = 0; index < sampleCount + warmupCount; index++) {
  const runId = process.env.BENCH_RUN_ID ? (sampleCount + warmupCount === 1 ? process.env.BENCH_RUN_ID : `${process.env.BENCH_RUN_ID}-${index}`) : `openclaw-${surface}-${mode}-${tools}-${process.pid}-${index}`;
  const prompt = suppliedPrompt !== undefined ? suppliedPrompt.replaceAll('{{RUN_ID}}', runId) : `BENCH_RUN_ID=${runId} BENCH_TOOL_COUNT=${tools} BENCH_DELAY_MS=${delay} BENCH_SURFACE=${surface} BENCH_TOOL_KIND=${surface === 'mcp' ? 'mcp' : 'terminal'}`;
  const messages = [];
  const runtime = {
    log: (...args) => messages.push({ kind: 'log', args }),
    error: (...args) => messages.push({ kind: 'error', args }),
    writeStdout: value => messages.push({ kind: 'stdout', value }),
    writeJson: value => messages.push({ kind: 'json', value }),
    exit: code => { throw new Error(`Unexpected runtime exit ${code}`); },
  };
  const start = performance.now();
  const result = await agentExecCommand(prompt, { cwd: workspace, stateDir: state, config: configPath, model: modelId, thinking: 'off', codeMode: 'direct', timeout: timeoutSeconds, json: true }, runtime);
  const end = performance.now();
  samples.push({ framework: 'openclaw', commit: '1b58cb9a1b4f4353e1add63c8506db4d890962e8', boundary: 'production agentExecCommand source API', native_owner_built: fs.existsSync(nativeOwner), surface, run_id: runId, sample: index - warmupCount, warmup: index < warmupCount, tool_count: tools, delay_ms: delay, elapsed_ms: end - start, rss_bytes: process.memoryUsage().rss, max_rss_kib: process.resourceUsage().maxRSS, result, messages });
  if (!result.envelope.ok) { process.exitCode = 1; break; }
}
const payload = { sample_count: sampleCount, warmup_count: warmupCount, samples };
if (process.env.BENCH_OUTPUT) fs.writeFileSync(process.env.BENCH_OUTPUT, JSON.stringify(payload, null, 2));
console.log(JSON.stringify(payload));
