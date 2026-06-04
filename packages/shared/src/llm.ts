export type LlmProtocol = 'anthropic' | 'openai';

export type LlmModelTiers = {
  light?: string;
  standard?: string;
  strong?: string;
};

export type LlmProfile = {
  id: string;
  name: string;
  protocol: LlmProtocol;
  baseUrl: string;
  models: LlmModelTiers;
  apiKeyEnvs?: string[];
};

export type ThreadModelSelection = {
  providerId: string;
  model: string | 'auto';
};

export type PiUserMessagePayload = {
  text: string;
  providerId: string;
  model: string | 'auto';
};

const WRITE_INTENT =
  /录制|停止|守护|同步|启动|关闭|start|stop|daemon|record|sync/i;
const READ_INTENT = /转写|摘要|manifest|场次|直播|transcript|summary|session/i;

export function firstConfiguredModel(profile: LlmProfile): string | undefined {
  return profile.models.light ?? profile.models.standard ?? profile.models.strong;
}

export function resolveAutoModel(text: string, profile: LlmProfile): string {
  const fallback = firstConfiguredModel(profile);
  if (!fallback) {
    throw new Error('当前 Provider 未配置任何模型 ID');
  }
  const trimmed = text.trim();
  const needsStrong = WRITE_INTENT.test(trimmed);
  if (needsStrong) {
    return profile.models.strong ?? profile.models.standard ?? profile.models.light ?? fallback;
  }
  if (READ_INTENT.test(trimmed)) {
    return profile.models.standard ?? profile.models.light ?? profile.models.strong ?? fallback;
  }
  return profile.models.light ?? profile.models.standard ?? profile.models.strong ?? fallback;
}

export function resolveUserModel(
  text: string,
  profile: LlmProfile,
  selection: { model: string | 'auto' },
): string {
  if (selection.model === 'auto') {
    return resolveAutoModel(text, profile);
  }
  return selection.model;
}
