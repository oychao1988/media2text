import {
  AuthStorage,
  createAgentSession,
  createSyntheticSourceInfo,
  DefaultResourceLoader,
  getAgentDir,
  ModelRegistry,
  SessionManager,
  type AgentSession,
  type Skill,
} from '@earendil-works/pi-coding-agent';
import type { Model } from '@earendil-works/pi-ai';
import { firstConfiguredModel } from '@m2t/shared';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  loadAgentConfig,
  readSkillDescription,
  resolveRepoRoot,
  resolveSkillsDirs,
  skillMdPath,
} from './config.js';
import {
  buildSystemPrompt,
  createInitialContext,
  hydrateContextFromApi,
  readContextModeFromEnv,
  readEnvContext,
  readRefreshAttachmentsFromEnv,
  readRefreshPathsFromEnv,
  type RuntimeContext,
} from './context.js';
import { applyUserMessageLlm, resolveModelObject } from './llm.js';
import { createM2tClient, createM2tTools, m2tToolNames } from './m2t-tools.js';
import {
  emitAssistantDelta,
  emitThinking,
  emitTurnEnd,
  emitTurnPhase,
  emitTurnStart,
} from './emit.js';
import { readSidecarLlmConfig, resolveProfileApiKey } from './llm-config.js';

export type M2tAgentSession = {
  session: AgentSession;
  reloadContext: () => Promise<void>;
  applyUserMessageLlm: (payload: import('./llm-config.js').UserMessageLlmPayload) => Promise<string>;
  beginUserTurn: () => void;
  dispose: () => void;
};

function loadSkills(repoRoot: string): Skill[] {
  const config = loadAgentConfig();
  const skills: Skill[] = [];
  for (const root of resolveSkillsDirs(config, repoRoot)) {
    for (const name of config.defaultSkills) {
      const md = skillMdPath(root, name);
      if (!md) continue;
      skills.push({
        name,
        description: readSkillDescription(md),
        filePath: md,
        baseDir: join(root, name),
        sourceInfo: createSyntheticSourceInfo(md, { source: 'media2text' }),
        disableModelInvocation: false,
      });
    }
  }
  return skills;
}

function resolveThinkingLevel(model: Model<any> | undefined): 'off' | 'low' {
  if (model && 'reasoning' in model && model.reasoning) return 'low';
  return 'off';
}

export async function createM2tAgentSession(
  onAssistantText: (text: string, meta: { durationMs: number; thinkingText: string }) => void,
): Promise<M2tAgentSession> {
  const repoRoot = resolveRepoRoot();
  let runtimeCtx: RuntimeContext = createInitialContext();
  const client = createM2tClient(runtimeCtx);
  const customTools = createM2tTools(client, runtimeCtx);

  const authStorage = AuthStorage.create();
  const modelRegistry = ModelRegistry.create(authStorage);
  const llmConfig = readSidecarLlmConfig();
  const defaultProfile =
    llmConfig.profiles.find((p) => p.id === llmConfig.defaultProviderId) ?? llmConfig.profiles[0];

  if (defaultProfile) {
    const defaultKey = resolveProfileApiKey(defaultProfile, llmConfig.keys);
    if (defaultKey) {
      if (defaultProfile.protocol === 'anthropic') {
        process.env.ANTHROPIC_API_KEY = defaultKey;
        process.env.ANTHROPIC_AUTH_TOKEN = defaultKey;
        if (defaultProfile.baseUrl.trim()) {
          process.env.ANTHROPIC_BASE_URL = defaultProfile.baseUrl.trim();
        }
        authStorage.setRuntimeApiKey('anthropic', defaultKey);
      } else {
        process.env.OPENAI_API_KEY = defaultKey;
        if (defaultProfile.baseUrl.trim()) {
          process.env.OPENAI_BASE_URL = defaultProfile.baseUrl.trim();
        }
        authStorage.setRuntimeApiKey('openai', defaultKey);
      }
    }
  }

  const available = await modelRegistry.getAvailable();
  let initialModel: Model<any> | undefined;
  if (defaultProfile) {
    const modelId = firstConfiguredModel(defaultProfile);
    if (modelId) {
      initialModel = resolveModelObject(modelRegistry, defaultProfile, modelId);
    }
  }
  if (!initialModel) {
    initialModel = available[0];
  }
  if (!initialModel) {
    throw new Error(
      '未配置 LLM API Key。请在系统配置 · AI 段添加 Provider，并在 .env 中设置 api_key_env。',
    );
  }

  const loader = new DefaultResourceLoader({
    cwd: repoRoot,
    agentDir: getAgentDir(),
    skillsOverride: (current) => ({
      skills: [...current.skills, ...loadSkills(repoRoot)],
      diagnostics: current.diagnostics,
    }),
    systemPromptOverride: () => buildSystemPrompt(runtimeCtx),
  });
  await loader.reload();

  const { session } = await createAgentSession({
    resourceLoader: loader,
    sessionManager: SessionManager.inMemory(repoRoot),
    authStorage,
    modelRegistry,
    model: initialModel,
    thinkingLevel: resolveThinkingLevel(initialModel),
    noTools: 'builtin',
    customTools,
    tools: m2tToolNames(),
  });

  let turnStartedAt = 0;
  let thinkingBuffer = '';
  let assistantBuffer = '';
  let lastEmittedAssistant = '';

  const unsubscribe = session.subscribe((event) => {
    if (event.type === 'agent_start') {
      turnStartedAt = Date.now();
      thinkingBuffer = '';
      assistantBuffer = '';
      emitTurnStart(turnStartedAt);
      emitTurnPhase('preparing', '准备中…');
      return;
    }

    if (event.type === 'message_update') {
      const ame = event.assistantMessageEvent;
      if (ame.type === 'thinking_delta') {
        thinkingBuffer += ame.delta;
        emitThinking(thinkingBuffer);
        emitTurnPhase('thinking', '思考中…');
      } else if (ame.type === 'text_delta') {
        assistantBuffer += ame.delta;
        emitAssistantDelta(ame.delta);
        emitTurnPhase('composing', '生成回复…');
      }
      return;
    }

    if (event.type === 'tool_execution_start') {
      const label = event.toolName ? `调用 ${event.toolName}…` : '调用工具…';
      emitTurnPhase('tool', label);
      return;
    }

    if (event.type === 'message_end') {
      const role =
        'message' in event && event.message && typeof event.message === 'object' && 'role' in event.message
          ? (event.message as { role?: string }).role
          : undefined;
      if (role && role !== 'assistant') {
        assistantBuffer = '';
        return;
      }
      const text = assistantBuffer.trim();
      assistantBuffer = '';
      if (!text || text === lastEmittedAssistant) return;
      lastEmittedAssistant = text;
      const durationMs = turnStartedAt > 0 ? Math.max(0, Date.now() - turnStartedAt) : 0;
      const thinkingText = thinkingBuffer.trim();
      thinkingBuffer = '';
      onAssistantText(text, { durationMs, thinkingText });
      return;
    }

    if (event.type === 'agent_end') {
      const durationMs = turnStartedAt > 0 ? Math.max(0, Date.now() - turnStartedAt) : 0;
      emitTurnEnd(durationMs);
      turnStartedAt = 0;
    }
  });

  async function reloadContext(): Promise<void> {
    Object.assign(
      runtimeCtx,
      readEnvContext(),
      readRefreshPathsFromEnv(),
      readRefreshAttachmentsFromEnv(),
    );
    runtimeCtx.contextMode = readContextModeFromEnv();
    await hydrateContextFromApi(runtimeCtx);
    await loader.reload();
  }

  await reloadContext();

  return {
    session,
    reloadContext,
    beginUserTurn: () => {
      assistantBuffer = '';
      lastEmittedAssistant = '';
      thinkingBuffer = '';
      turnStartedAt = Date.now();
      emitTurnStart(turnStartedAt);
      emitTurnPhase('preparing', '准备中…');
    },
    applyUserMessageLlm: (payload) =>
      applyUserMessageLlm(authStorage, modelRegistry, session, payload),
    dispose: unsubscribe,
  };
}

export function readSidecarVersion(): string {
  const fromEnv = process.env.M2T_AGENT_SIDECAR_VERSION?.trim();
  if (fromEnv) return fromEnv;
  try {
    const versionPath = join(
      resolveRepoRoot(),
      'apps/m2t-desktop/src-tauri/resources/agent/VERSION',
    );
    return readFileSync(versionPath, 'utf8').trim();
  } catch {
    return '0.1.0';
  }
}
