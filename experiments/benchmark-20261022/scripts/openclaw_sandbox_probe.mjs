import fs from 'node:fs';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import { pathToFileURL } from 'node:url';
const root = path.resolve(import.meta.dirname, '..');
const source = path.join(root, 'sources/openclaw');
const { ensureSandboxContainer, execContainer, DOCKER_SANDBOX_ENGINE: engine } = await import(pathToFileURL(path.join(source, 'src/agents/sandbox/docker.ts')));
const { resolveSandboxConfigForAgent } = await import(pathToFileURL(path.join(source, 'src/agents/sandbox/config.ts')));
const image = 'python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70';
const workspace = path.join(root, 'fixtures/docker-workspace');
fs.mkdirSync(workspace, { recursive: true });
const config = { agents: { defaults: { sandbox: { mode: 'all', scope: 'session', workspaceAccess: 'rw', docker: { image, containerPrefix: 'oc-bench-', network: 'none', memory: '512m', memorySwap: process.argv[2] === 'quota' ? '512m' : undefined, cpus: 1, pidsLimit: 128, readOnlyRoot: false, tmpfs: [] } } } } };
const cfg = resolveSandboxConfigForAgent(config);
const mode = process.argv[2] ?? 'smoke';
const oneShot = ['smoke', 'quota'].includes(mode);
const sampleCount = oneShot ? 1 : Number(process.env.BENCH_SAMPLES ?? 30);
const warmupCount = oneShot ? 0 : Number(process.env.BENCH_WARMUPS ?? 5);
if (!Number.isSafeInteger(sampleCount) || sampleCount < 1 || !Number.isSafeInteger(warmupCount) || warmupCount < 0 || (mode === 'warm' && warmupCount < 1)) throw new Error('Invalid benchmark sample/warmup count');
const count = sampleCount + warmupCount;
const samples = [];
let reused;
let verification;
try {
  for (let index = 0; index < count; index++) {
    const scopeKey = mode === 'cold' ? `bench-cold-${process.pid}-${index}` : `bench-warm-${process.pid}`;
    const start = performance.now();
    const container = await ensureSandboxContainer({ engine, scopeKey, workspaceDir: workspace, agentWorkspaceDir: workspace, cfg });
    const ready = performance.now();
    const result = await execContainer(engine, ['exec', container.containerId, 'sh', '-lc', 'printf BENCH_READY']);
    const end = performance.now();
    if (!verification) {
      const inspected = await execContainer(engine, ['inspect', container.containerId]);
      const full = JSON.parse(inspected.stdout)[0];
      const inspectedImage = JSON.parse((await execContainer(engine, ['image', 'inspect', image])).stdout)[0];
      const expectedDigest = image.split('@')[1];
      const checks = { cpu: full.HostConfig.NanoCpus === 1000000000, memory: full.HostConfig.Memory === 536870912, pids: full.HostConfig.PidsLimit === 128, network: full.HostConfig.NetworkMode === 'none', writable_root: full.HostConfig.ReadonlyRootfs === false, shm: full.HostConfig.ShmSize === 67108864, image: full.Image === inspectedImage.Id && inspectedImage.RepoDigests.some(x => x.endsWith(`@${expectedDigest}`)) };
      verification = { checks, host_config: full.HostConfig, mounts: full.Mounts, config: full.Config, image_id: full.Image, image_repo_digests: inspectedImage.RepoDigests };
    }
    const record = { framework: 'openclaw', commit: '1b58cb9a1b4f4353e1add63c8506db4d890962e8', row: mode === 'quota' ? 26 : 6, mode, image, sample: index - warmupCount, warmup: index < warmupCount, ensure_ms: ready - start, first_command_ms: end - ready, ready_ms: end - start, ready_latency_ms: end - start, correct: result.code === 0 && result.stdout === 'BENCH_READY', marker_correct: result.code === 0 && result.stdout === 'BENCH_READY', container_id: container.containerId, container_reused: reused === container.containerId };
    samples.push(record);
    if (mode === 'cold') await execContainer(engine, ['rm', '-f', container.containerId]);
    else reused = container.containerId;
  }
} finally {
  if (reused && mode !== 'quota') await execContainer(engine, ['rm', '-f', reused]);
}
const measured = samples.filter(sample => !sample.warmup);
const aggregate = { expected_samples: sampleCount, measured_samples: measured.length, warmup_samples: warmupCount, markers_correct: samples.every(sample => sample.correct), native_reuse_correct: mode !== 'warm' || measured.every(sample => sample.container_reused && sample.container_id === samples[0].container_id), cold_ids_unique: mode !== 'cold' || new Set(samples.map(sample => sample.container_id)).size === samples.length, inspected_config_correct: Object.values(verification.checks).every(Boolean) };
aggregate.valid = aggregate.measured_samples === aggregate.expected_samples && aggregate.markers_correct && aggregate.native_reuse_correct && aggregate.cold_ids_unique && aggregate.inspected_config_correct;
console.log(JSON.stringify({ config: cfg, verification, aggregate, samples }));
if (!aggregate.valid) process.exitCode = 1;
