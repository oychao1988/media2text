import { parsePiEventLine, type LlmProfile, type PiEvent, type PiUserMessagePayload } from '@m2t/shared';
import { apiGet, getApiBaseUrl } from '../../lib/api';
import type { ConfigDto, LlmProvider } from '../../lib/types';

export const M2T_AGENT_SIDECAR_VERSION = import.meta.env.VITE_M2T_AGENT_SIDECAR_VERSION ?? '0.1.0';

const RUNTIME_KEY = '__m2t_agent_sidecar_state__';

function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

export type AgentSidecarEnv = Record<string, string>;

/** @internal exported for unit tests */
export function buildLlmKeysFromProviders(providers: LlmProvider[]): Record<string, string> {
  const keys: Record<string, string> = {};
  for (const p of providers) {
    const key = p.api_key?.trim();
    if (key) keys[p.name] = key;
  }
  return keys;
}

/** Mirror .env vars so agent sidecar can resolve keys without reading project files. */
export function buildProviderEnvVars(providers: LlmProvider[]): Record<string, string> {
  const env: Record<string, string> = {};
  for (const p of providers) {
    const key = p.api_key?.trim();
    if (!key) continue;
    for (const envName of p.api_key_envs ?? []) {
      const name = envName.trim();
      if (name) env[name] = key;
    }
  }
  return env;
}

function providersToProfiles(providers: LlmProvider[]): LlmProfile[] {
  return providers.map((p) => {
    const models = p.models ?? [];
    return {
      id: p.name,
      name: p.name,
      protocol: 'openai',
      baseUrl: p.base_url,
      apiKeyEnvs: p.api_key_envs,
      models: {
        light: models[0],
        standard: models[1] ?? models[0],
        strong: models[models.length - 1] ?? models[0],
      },
    };
  });
}

export type AgentContext = {
  creatorId?: string;
  sessionId?: string;
  threadId?: string;
  workspace?: string;
};

export async function buildAgentSidecarEnv(ctx: AgentContext = {}): Promise<AgentSidecarEnv> {
  let config: ConfigDto | null = null;
  try {
    const res = await apiGet<{ ok: boolean; config: ConfigDto }>('/api/config', true);
    config = res.config;
  } catch {
    config = null;
  }

  const providers = config?.llmProviders ?? [];
  const profiles = providers.length ? providersToProfiles(providers) : [];
  const llmKeys = buildLlmKeysFromProviders(providers);
  const env: AgentSidecarEnv = {
    M2T_AGENT_SIDECAR_VERSION,
    M2T_API_BASE_URL: await getApiBaseUrl(),
    M2T_WORKSPACE: ctx.workspace ?? './data',
    M2T_CREATOR_ID: ctx.creatorId ?? '',
    M2T_SESSION_ID: ctx.sessionId ?? '',
    M2T_THREAD_ID: ctx.threadId ?? '',
    M2T_LLM_PROFILES: JSON.stringify(profiles),
    M2T_LLM_KEYS: JSON.stringify(llmKeys),
    M2T_LLM_DEFAULT_PROVIDER_ID: config?.activeProviderId ?? '',
    ...buildProviderEnvVars(providers),
  };

  if (isTauri()) {
    const { resolveResource } = await import('@tauri-apps/api/path');
    try {
      env.M2T_SKILLS_ROOT = await resolveResource('agent-skills');
      env.M2T_AGENT_CONFIG = await resolveResource('agent/agent.json');
    } catch {
      // dev fallback
    }
  }

  return env;
}

let sidecarScriptPath: string | null = null;

async function ensureSidecarPaths(ctx: AgentContext): Promise<{
  scriptPath: string;
  envVars: AgentSidecarEnv;
}> {
  const envVars = await buildAgentSidecarEnv(ctx);
  if (!sidecarScriptPath) {
    const { invoke } = await import('@tauri-apps/api/core');
    sidecarScriptPath = await invoke<string>('resolve_agent_sidecar_script');
  }
  return { scriptPath: sidecarScriptPath, envVars };
}

type SidecarSubscriber = (event: PiEvent) => void;
type SidecarLifecycleListener = (phase: 'crashed' | 'recovering') => void;

type AgentSidecarRuntime = {
  activeSubscriber: SidecarSubscriber | null;
  subscriberCount: number;
  lifecycleListeners: Set<SidecarLifecycleListener>;
  listenersReady: boolean;
  eventUnlisten: (() => void) | null;
  exitUnlisten: (() => void) | null;
  recoverTimer: ReturnType<typeof setTimeout> | undefined;
  sidecarRunning: boolean;
  recoverInFlight: boolean;
  suppressExitRecoveryUntil: number;
  pendingReload: boolean;
  lastContext: AgentContext;
};

function getRuntime(): AgentSidecarRuntime {
  const root = globalThis as typeof globalThis & { [RUNTIME_KEY]?: AgentSidecarRuntime };
  if (!root[RUNTIME_KEY]) {
    root[RUNTIME_KEY] = {
      activeSubscriber: null,
      subscriberCount: 0,
      lifecycleListeners: new Set(),
      listenersReady: false,
      eventUnlisten: null,
      exitUnlisten: null,
      recoverTimer: undefined,
      sidecarRunning: false,
      recoverInFlight: false,
      suppressExitRecoveryUntil: 0,
      pendingReload: false,
      lastContext: {},
    };
  }
  return root[RUNTIME_KEY];
}

const INTENTIONAL_STOP_GRACE_MS = 4000;

function markIntentionalStop(ms = INTENTIONAL_STOP_GRACE_MS): void {
  getRuntime().suppressExitRecoveryUntil = Date.now() + ms;
}

function shouldRecoverFromExit(): boolean {
  return Date.now() > getRuntime().suppressExitRecoveryUntil;
}

export function requestAgentReload(): void {
  getRuntime().pendingReload = true;
  window.dispatchEvent(new CustomEvent('m2t-agent-reload-requested'));
}

export function onAgentReloadRequested(listener: () => void): () => void {
  const handler = () => listener();
  window.addEventListener('m2t-agent-reload-requested', handler);
  return () => window.removeEventListener('m2t-agent-reload-requested', handler);
}

export async function flushPendingAgentReload(): Promise<void> {
  const rt = getRuntime();
  if (!rt.pendingReload || !isTauri()) return;
  rt.pendingReload = false;
  await restartAgentSidecar(rt.lastContext);
}

async function invokeStart(ctx: AgentContext): Promise<void> {
  const { invoke } = await import('@tauri-apps/api/core');
  const { scriptPath, envVars } = await ensureSidecarPaths(ctx);
  markIntentionalStop();
  await invoke('start_agent_sidecar', { scriptPath, envVars });
  getRuntime().sidecarRunning = true;
  getRuntime().lastContext = ctx;
}

async function invokeStop(): Promise<void> {
  const rt = getRuntime();
  if (!rt.sidecarRunning) return;
  const { invoke } = await import('@tauri-apps/api/core');
  markIntentionalStop();
  await invoke('stop_agent_sidecar');
  rt.sidecarRunning = false;
}

export async function restartAgentSidecar(ctx: AgentContext = getRuntime().lastContext): Promise<void> {
  if (!isTauri()) return;
  const { invoke } = await import('@tauri-apps/api/core');
  const { scriptPath, envVars } = await ensureSidecarPaths(ctx);
  markIntentionalStop();
  await invoke('restart_agent_sidecar', { scriptPath, envVars });
  getRuntime().sidecarRunning = true;
  getRuntime().lastContext = ctx;
}

async function ensureListeners(): Promise<void> {
  if (!isTauri()) return;
  const rt = getRuntime();
  if (rt.listenersReady) return;
  const { listen } = await import('@tauri-apps/api/event');
  rt.eventUnlisten = await listen<string>('agent-event', (e) => {
    const parsed = parsePiEventLine(e.payload);
    if (parsed) rt.activeSubscriber?.(parsed);
  });
  rt.exitUnlisten = await listen('agent-sidecar-exited', () => {
    rt.sidecarRunning = false;
    if (!shouldRecoverFromExit()) return;
    if (rt.subscriberCount === 0) return;
    for (const l of rt.lifecycleListeners) l('crashed');
    if (rt.recoverTimer) clearTimeout(rt.recoverTimer);
    rt.recoverTimer = setTimeout(() => {
      rt.recoverTimer = undefined;
      void recoverSidecar();
    }, 1500);
  });
  rt.listenersReady = true;
}

async function recoverSidecar(): Promise<void> {
  const rt = getRuntime();
  if (!isTauri() || rt.subscriberCount === 0 || rt.recoverInFlight) return;
  rt.recoverInFlight = true;
  for (const l of rt.lifecycleListeners) l('recovering');
  try {
    await restartAgentSidecar(rt.lastContext);
  } catch {
    for (const l of rt.lifecycleListeners) l('crashed');
  } finally {
    rt.recoverInFlight = false;
  }
}

export function onAgentSidecarLifecycle(listener: SidecarLifecycleListener): () => void {
  const rt = getRuntime();
  rt.lifecycleListeners.add(listener);
  return () => rt.lifecycleListeners.delete(listener);
}

export async function startAgentSidecar(
  onEvent: (event: PiEvent) => void,
  ctx: AgentContext = {},
): Promise<() => Promise<void>> {
  if (!isTauri()) {
    onEvent({ type: 'sidecar.ready', payload: { version: M2T_AGENT_SIDECAR_VERSION } });
    return async () => {};
  }

  const rt = getRuntime();
  rt.activeSubscriber = onEvent;
  rt.subscriberCount += 1;
  rt.lastContext = ctx;
  await ensureListeners();
  if (!rt.sidecarRunning) {
    await invokeStart(ctx);
  } else {
    await sendAgentContextRefresh(ctx);
  }

  return async () => {
    if (rt.activeSubscriber === onEvent) rt.activeSubscriber = null;
    rt.subscriberCount = Math.max(0, rt.subscriberCount - 1);
    if (rt.subscriberCount === 0) {
      if (rt.recoverTimer) {
        clearTimeout(rt.recoverTimer);
        rt.recoverTimer = undefined;
      }
      // React Strict Mode remounts immediately; defer stop to avoid EPIPE mid-handshake.
      await new Promise((resolve) => setTimeout(resolve, 150));
      if (rt.subscriberCount > 0) return;
      await invokeStop();
    }
  };
}

export async function sendAgentUserMessage(payload: PiUserMessagePayload): Promise<void> {
  if (!isTauri()) return;
  const { invoke } = await import('@tauri-apps/api/core');
  await invoke('send_agent_user_message', { payload });
}

export async function sendAgentContextRefresh(ctx: AgentContext): Promise<void> {
  if (!isTauri()) return;
  getRuntime().lastContext = ctx;
  const { invoke } = await import('@tauri-apps/api/core');
  await invoke('send_agent_context_refresh', {
    payload: {
      creatorId: ctx.creatorId ?? '',
      sessionId: ctx.sessionId ?? '',
      threadId: ctx.threadId ?? '',
    },
  });
}

/** @internal */
export function __resetAgentSidecarRuntimeForTests(): void {
  const root = globalThis as typeof globalThis & { [RUNTIME_KEY]?: AgentSidecarRuntime };
  delete root[RUNTIME_KEY];
}
