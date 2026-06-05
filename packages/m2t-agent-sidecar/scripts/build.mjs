import { build } from 'esbuild';
import { cpSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const pkgRoot = join(__dirname, '..');
const repoRoot = join(pkgRoot, '../..');
const resourcesRoot = join(repoRoot, 'apps/m2t-desktop/src-tauri/resources');
const outFile = join(resourcesRoot, 'agent/sidecar.bundle.mjs');

mkdirSync(dirname(outFile), { recursive: true });
mkdirSync(join(resourcesRoot, 'agent'), { recursive: true });

cpSync(join(repoRoot, 'packages/agent-skills'), join(resourcesRoot, 'agent-skills'), {
  recursive: true,
});
cpSync(join(repoRoot, 'apps/m2t-desktop/agent/agent.json'), join(resourcesRoot, 'agent/agent.json'));
writeFileSync(join(resourcesRoot, 'agent/VERSION'), '0.1.0\n', 'utf8');

await build({
  entryPoints: [join(pkgRoot, 'src/main.ts')],
  outfile: outFile,
  bundle: true,
  platform: 'node',
  format: 'esm',
  target: 'node20',
  sourcemap: true,
  external: [],
  // CJS deps (cross-spawn) call require(); default import avoids clashing with bundled createRequire imports.
  banner: {
    js: "import nodeModule from 'node:module'; const require = nodeModule.createRequire(import.meta.url);",
  },
});

console.log(`Built ${outFile}`);
