#!/usr/bin/env node
/**
 * A9 smoke: spawn bundled agent sidecar, wait for sidecar.ready, send one user message.
 * Exit 0 if assistant or delta received within timeout.
 */
import { execSync } from 'node:child_process';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const API = process.env.M2T_API_BASE_URL ?? 'http://127.0.0.1:8765';
const TIMEOUT_MS = Number(process.env.M2T_AGENT_SMOKE_TIMEOUT_MS ?? 180000);
const __dirname = dirname(fileURLToPath(import.meta.url));
const sidecarScript = join(
  __dirname,
  '../apps/m2t-desktop/src-tauri/resources/agent/sidecar.bundle.mjs',
);

async function fetchJson(path) {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${path} HTTP ${res.status}`);
  return res.json();
}

function buildEnv(config) {
  const providers = config.llmProviders ?? [];
  const profiles = providers.map((p) => ({
    id: p.name,
    name: p.name,
    protocol: 'openai',
    baseUrl: p.base_url,
    apiKeyEnvs: p.api_key_envs,
    models: {
      light: p.models?.[0],
      standard: p.models?.[1] ?? p.models?.[0],
      strong: p.models?.[p.models.length - 1] ?? p.models?.[0],
    },
  }));
  const llmKeys = {};
  const extra = {};
  for (const p of providers) {
    const key = p.api_key?.trim();
    if (key) llmKeys[p.name] = key;
    for (const envName of p.api_key_envs ?? []) {
      if (key && envName.trim()) extra[envName.trim()] = key;
    }
  }
  return {
    ...process.env,
    ...extra,
    M2T_API_BASE_URL: API,
    M2T_WORKSPACE: config.workspace ?? './data',
    M2T_LLM_PROFILES: JSON.stringify(profiles),
    M2T_LLM_KEYS: JSON.stringify(llmKeys),
    M2T_LLM_DEFAULT_PROVIDER_ID: config.activeProviderId ?? '',
  };
}

function runSidecarSmoke(child, userLine, timeoutMs) {
  return new Promise((resolve, reject) => {
    const rl = createInterface({ input: child.stdout });
    let ready = false;
    let sent = false;
    const timer = setTimeout(() => {
      rl.close();
      reject(new Error(`A9 smoke timeout after ${timeoutMs}ms (ready=${ready}, sent=${sent})`));
    }, timeoutMs);

    rl.on('line', (line) => {
      let event;
      try {
        event = JSON.parse(line);
      } catch {
        return;
      }
      if (event.type === 'sidecar.ready') {
        ready = true;
        if (!sent) {
          sent = true;
          child.stdin.write(`${userLine}\n`);
        }
        return;
      }
      if (event.type === 'error' && !ready) {
        // Init may emit error before ready; keep listening.
        return;
      }
      if (event.type === 'error' && sent) {
        clearTimeout(timer);
        rl.close();
        reject(new Error(event.payload?.message ?? 'sidecar error'));
        return;
      }
      if (event.type === 'message.assistant' || event.type === 'message.assistant.delta') {
        clearTimeout(timer);
        rl.close();
        resolve(event);
      }
    });

    child.stderr?.on('data', (buf) => {
      process.stderr.write(buf);
    });
  });
}

function agentSidecarAlreadyRunning() {
  try {
    const out = execSync('pgrep -f sidecar.bundle.mjs 2>/dev/null || true', {
      encoding: 'utf8',
    }).trim();
    return out.length > 0;
  } catch {
    return false;
  }
}

async function main() {
  const { config } = await fetchJson('/api/config');
  if (!config?.llmProviders?.some((p) => p.configured && p.api_key)) {
    console.error('A9 SKIP: no configured LLM provider with api_key');
    process.exit(2);
  }

  if (agentSidecarAlreadyRunning()) {
    console.log(
      'A9 SKIP: agent sidecar already running (e.g. Tauri dev); send one message in Desktop to complete UI path',
    );
    process.exit(0);
  }

  const child = spawn(process.execPath, [sidecarScript], {
    env: buildEnv(config),
    stdio: ['pipe', 'pipe', 'inherit'],
    cwd: join(__dirname, '..'),
  });

  const userLine = JSON.stringify({
    type: 'message.user',
    payload: {
      text: '验收冒烟：请只回复 OK',
      model: 'auto',
      providerId: config.activeProviderId ?? '',
    },
  });

  const event = await runSidecarSmoke(child, userLine, TIMEOUT_MS);
  child.kill('SIGTERM');
  console.log('A9 PASS:', event.type, JSON.stringify(event.payload).slice(0, 120));
}

main().catch((err) => {
  console.error('A9 FAIL:', err.message);
  process.exit(1);
});
