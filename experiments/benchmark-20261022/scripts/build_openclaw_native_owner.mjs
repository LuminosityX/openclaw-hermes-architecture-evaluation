import path from 'node:path';
import { pathToFileURL } from 'node:url';
const root = path.resolve(import.meta.dirname, '..');
const source = path.join(root, 'sources/openclaw');
const { default: configs } = await import(pathToFileURL(path.join(source, 'tsdown.config.ts')));
const { build } = await import(pathToFileURL(path.join(source, 'node_modules/tsdown/dist/index.mjs')));
const selected = configs.filter(config => {
  const names = Object.keys(config.entry ?? {});
  return names.length === 1 && names[0] === 'process/supervisor/service-child-group-anchor';
});
if (selected.length !== 1) throw new Error(`Expected one canonical native owner config, got ${selected.length}`);
// Reuse the repository's exact standalone native-owner build configuration.
// Do not clean other artifacts or run the full runtime build.
await build({ ...selected[0], config: false, clean: false });
console.log(JSON.stringify({ artifact: path.join(source, 'dist/process/supervisor/service-child-group-anchor.js') }));
