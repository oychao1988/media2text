import type { LlmProfile } from '@m2t/shared';

export type SidecarLlmConfig = {
  profiles: LlmProfile[];
  keys: Record<string, string>;
  defaultProviderId: string | null;
};

export type UserMessageLlmPayload = {
  text: string;
  providerId: string;
  model: string | 'auto';
};

function readJsonEnv<T>(name: string, fallback: T): T {
  const raw = process.env[name]?.trim();
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function readSidecarLlmConfig(): SidecarLlmConfig {
  return {
    profiles: readJsonEnv<LlmProfile[]>('M2T_LLM_PROFILES', []),
    keys: readJsonEnv<Record<string, string>>('M2T_LLM_KEYS', {}),
    defaultProviderId: process.env.M2T_LLM_DEFAULT_PROVIDER_ID?.trim() || null,
  };
}

export function findProfile(config: SidecarLlmConfig, providerId: string): LlmProfile | undefined {
  return config.profiles.find((p) => p.id === providerId);
}

export function resolveProfileApiKey(profile: LlmProfile, keys: Record<string, string>): string {
  const fromKeys = keys[profile.id]?.trim();
  if (fromKeys) return fromKeys;
  for (const envName of profile.apiKeyEnvs ?? []) {
    const v = process.env[envName]?.trim();
    if (v) return v;
  }
  return '';
}
