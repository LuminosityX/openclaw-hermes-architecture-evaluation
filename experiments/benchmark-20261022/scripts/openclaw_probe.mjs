import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { performance } from 'node:perf_hooks';
import { pathToFileURL } from 'node:url';

const root = path.resolve(import.meta.dirname, '..');
const source = path.join(root, 'sources/openclaw');
const { loadWorkspaceSkills } = await import(pathToFileURL(path.join(source, 'src/skills/loading/workspace-skill-loader.ts')));
const { loadSingleSkillDirectory } = await import(pathToFileURL(path.join(source, 'src/skills/loading/local-loader.ts')));
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'fixtures/manifest.json'), 'utf8'));
const mode = process.argv[2] ?? 'smoke';
const size = Number(process.argv[3] ?? 10);
const fixture = manifest.fixtures.find(x => x.size === size);
if (!fixture) throw new Error(`Unknown fixture size ${size}`);
const workspace = path.join(root, 'envs/openclaw-workspaces', String(size));
fs.mkdirSync(workspace, { recursive: true });
const skillRoot = path.join(workspace, 'skills');
if (!fs.existsSync(skillRoot)) fs.cpSync(fixture.path, skillRoot, { recursive: true });
const configured = process.argv[4] !== 'default';
const options = {
  workspaceOnly: true,
  config: configured ? { skills: { limits: { maxCandidatesPerRoot: 1000, maxSkillsLoadedPerSource: 1000, maxSkillFileBytes: 256000 } } } : undefined,
};
const wanted = new Map(fixture.entries.map(x => [x.name, x]));
const selected = [fixture.entries[0], fixture.entries[Math.floor(size / 2)], fixture.entries.at(-1)];
const sha = content => crypto.createHash('sha256').update(content).digest('hex');
function sample(index, phase) {
  const start = performance.now();
  const entries = loadWorkspaceSkills(workspace, options);
  const discoveryMs = performance.now() - start;
  const discoveredNames = entries.map(x => x.skill.name).sort();
  const catalogCorrect = entries.length === size && new Set(discoveredNames).size === size && entries.every(x => wanted.get(x.skill.name)?.skill_sha256 === x.skill.contentHash);
  const readStart = performance.now();
  const reads = selected.map(entry => loadSingleSkillDirectory({ skillDir: path.join(skillRoot, entry.name), source: 'openclaw-workspace', rootRealPath: skillRoot, maxBytes: 256000 }));
  const readMs = performance.now() - readStart;
  const readsCorrect = reads.every((entry, i) => entry && entry.skill.name === selected[i].name && sha(entry.content) === selected[i].skill_sha256);
  return { framework: 'openclaw', commit: '1b58cb9a1b4f4353e1add63c8506db4d890962e8', row: 23, size, mode: phase, configured_limits: configured, sample: index, discovery_ms: discoveryMs, read_three_skills_ms: readMs, discovered_count: entries.length, catalog_correct: catalogCorrect, reads_correct: readsCorrect, discovered_names: index === 0 ? discoveredNames : undefined, rss_bytes: process.memoryUsage().rss, cpu_us: process.cpuUsage(), max_rss_kib: process.resourceUsage().maxRSS };
}
if (mode === 'warm') {
  const warmups = Number(process.env.BENCH_WARMUPS ?? 5);
  const count = Number(process.env.BENCH_SAMPLES ?? 30);
  if (!Number.isSafeInteger(warmups) || warmups < 0 || !Number.isSafeInteger(count) || count < 1) throw new Error('Invalid sample/warmup count');
  for (let i = 0; i < warmups; i++) sample(i, 'warmup');
  const samples = Array.from({ length: count }, (_, i) => sample(i, 'warm'));
  console.log(JSON.stringify({ samples }));
} else {
  console.log(JSON.stringify(sample(0, mode === 'cold' ? 'cold_process_cache_os_warm' : mode)));
}
