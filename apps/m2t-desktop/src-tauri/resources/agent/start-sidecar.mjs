#!/usr/bin/env node
/**
 * media2text Agent sidecar launcher (align scmclaw pi/start-sidecar.mjs).
 */
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

function findRepoRoot(start) {
  let dir = start;
  for (let i = 0; i < 12; i += 1) {
    if (existsSync(join(dir, 'pnpm-workspace.yaml'))) return dir;
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

function resolveLaunch() {
  const repoFromEnv = process.env.M2T_REPO_ROOT?.trim();
  const repoRoot =
    (repoFromEnv && existsSync(repoFromEnv) ? repoFromEnv : null) ??
    findRepoRoot(__dirname) ??
    findRepoRoot(process.cwd());

  if (repoRoot) {
    const tsxBin = join(repoRoot, 'node_modules/.bin/tsx');
    const mainTs = join(repoRoot, 'packages/m2t-agent-sidecar/src/main.ts');
    if (existsSync(tsxBin) && existsSync(mainTs)) {
      return { command: tsxBin, args: [mainTs], cwd: repoRoot };
    }
  }

  const bundled = join(__dirname, 'sidecar.bundle.mjs');
  if (existsSync(bundled)) {
    return { command: process.execPath, args: [bundled], cwd: __dirname };
  }

  process.stderr.write(
    'm2t-agent-sidecar 启动失败：未找到 monorepo / tsx，且无 sidecar.bundle.mjs。\n' +
      '请在仓库根目录执行: pnpm install && pnpm --filter @media2text/m2t-agent-sidecar build\n',
  );
  process.exit(1);
}

const launch = resolveLaunch();
const child = spawn(launch.command, launch.args, {
  cwd: launch.cwd,
  env: process.env,
  stdio: ['pipe', 'pipe', 'inherit'],
});

child.stdout.pipe(process.stdout);
process.stdin.pipe(child.stdin);

child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
});

child.on('error', (err) => {
  process.stderr.write(`m2t-agent-sidecar spawn 失败: ${err.message}\n`);
  process.exit(1);
});
