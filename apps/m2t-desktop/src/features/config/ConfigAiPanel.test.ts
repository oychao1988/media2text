import { describe, expect, it } from 'vitest';
import { llmProvidersForPatch } from './ConfigAiPanel';
import type { LlmProvider } from '../../lib/types';

const base: LlmProvider = {
  name: 'nvidia',
  base_url: 'https://integrate.api.nvidia.com/v1',
  api_key_envs: ['NVIDIA_API_KEY'],
  models: ['m1'],
  configured: true,
  connected: null,
  api_key: null,
};

describe('llmProvidersForPatch', () => {
  it('includes a newly entered api key', () => {
    const out = llmProvidersForPatch([{ ...base, api_key: 'nvapi-secret' }]);
    expect(out[0]?.api_key).toBe('nvapi-secret');
  });

  it('omits masked placeholder keys', () => {
    const out = llmProvidersForPatch([{ ...base, api_key: '***' }]);
    expect(out[0]).not.toHaveProperty('api_key');
  });

  it('strips configured/connected from payload', () => {
    const out = llmProvidersForPatch([{ ...base, connected: true, api_key: 'k' }]);
    expect(out[0]).not.toHaveProperty('configured');
    expect(out[0]).not.toHaveProperty('connected');
  });
});
