import type { Model } from '@earendil-works/pi-ai';
import type { AuthStorage, ModelRegistry } from '@earendil-works/pi-coding-agent';
import type { LlmProfile } from '@m2t/shared';
import { resolveUserModel } from '@m2t/shared';
import {
  findProfile,
  readSidecarLlmConfig,
  resolveProfileApiKey,
  type UserMessageLlmPayload,
} from './llm-config.js';

export type { SidecarLlmConfig, UserMessageLlmPayload } from './llm-config.js';
export { findProfile, readSidecarLlmConfig } from './llm-config.js';

function providerName(protocol: LlmProfile['protocol']): string {
  return protocol === 'anthropic' ? 'anthropic' : 'openai';
}

function applyProtocolEnv(profile: LlmProfile, apiKey: string): void {
  if (profile.protocol === 'anthropic') {
    process.env.ANTHROPIC_API_KEY = apiKey;
    process.env.ANTHROPIC_AUTH_TOKEN = apiKey;
    if (profile.baseUrl.trim()) {
      process.env.ANTHROPIC_BASE_URL = profile.baseUrl.trim();
    }
    return;
  }
  process.env.OPENAI_API_KEY = apiKey;
  if (profile.baseUrl.trim()) {
    process.env.OPENAI_BASE_URL = profile.baseUrl.trim();
  }
}

export function resolveModelObject(
  registry: ModelRegistry,
  profile: LlmProfile,
  modelId: string,
): Model<any> | undefined {
  const provider = providerName(profile.protocol);
  const fromRegistry = registry.find(provider, modelId);
  if (fromRegistry) return fromRegistry;
  return {
    provider,
    id: modelId,
    name: modelId,
    api: profile.protocol === 'anthropic' ? 'anthropic-messages' : 'openai-completions',
    baseUrl: profile.baseUrl.trim(),
    reasoning: false,
    input: ['text'],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 204_800,
    maxTokens: 8_192,
  } as Model<any>;
}

export async function applyUserMessageLlm(
  authStorage: AuthStorage,
  modelRegistry: ModelRegistry,
  session: { setModel: (model: Model<any>) => Promise<void> },
  payload: UserMessageLlmPayload,
): Promise<string> {
  const config = readSidecarLlmConfig();
  const providerId =
    payload.providerId || config.defaultProviderId || config.profiles[0]?.id || '';
  const profile = findProfile(config, providerId);
  if (!profile) {
    throw new Error('未找到 LLM Provider，请在系统配置 · AI 段添加并设为默认。');
  }

  const apiKey = resolveProfileApiKey(profile, config.keys);
  if (!apiKey) {
    throw new Error(
      '当前 Provider 未配置 API Key。请在项目 .env 中设置对应环境变量，或在桌面端保存 Key。',
    );
  }

  applyProtocolEnv(profile, apiKey);
  authStorage.setRuntimeApiKey(providerName(profile.protocol), apiKey);

  const resolvedModelId = resolveUserModel(payload.text, profile, {
    model: payload.model,
  });
  const model = resolveModelObject(modelRegistry, profile, resolvedModelId);
  if (!model) {
    throw new Error(`无法解析模型：${resolvedModelId}`);
  }
  await session.setModel(model);
  return resolvedModelId;
}
