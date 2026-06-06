import { describe, expect, it } from 'vitest';
import { buildAgentModelCatalog } from './agentModelCatalog';

describe('buildAgentModelCatalog', () => {
  it('maps each model to its provider', () => {
    const { models, providerByModel } = buildAgentModelCatalog([
      {
        name: 'nvidia',
        base_url: 'https://example.com',
        models: ['glm', 'deepseek-ai/deepseek-v4-pro'],
        configured: true,
      },
      {
        name: 'DeepSeek',
        base_url: 'https://api.deepseek.com',
        models: ['deepseek-chat'],
        configured: true,
      },
    ]);
    expect(models).toEqual(['glm', 'deepseek-ai/deepseek-v4-pro', 'deepseek-chat']);
    expect(providerByModel.get('deepseek-chat')).toBe('DeepSeek');
    expect(providerByModel.get('glm')).toBe('nvidia');
  });
});
