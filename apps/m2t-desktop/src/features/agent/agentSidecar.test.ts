import { describe, expect, it } from 'vitest';
import {
  buildContextRefreshPayload,
  buildLlmKeysFromProviders,
  buildProviderEnvVars,
} from './agentSidecar';
import type { LlmProvider } from '../../lib/types';

const sampleProviders: LlmProvider[] = [
  {
    name: 'nvidia',
    base_url: 'https://integrate.api.nvidia.com/v1',
    api_key_envs: ['NVIDIA_API_KEY'],
    models: ['z-ai/glm-5.1'],
    configured: true,
    api_key: 'nvapi-test-key',
  },
];

describe('buildLlmKeysFromProviders', () => {
  it('maps provider name to api_key', () => {
    expect(buildLlmKeysFromProviders(sampleProviders)).toEqual({
      nvidia: 'nvapi-test-key',
    });
  });

  it('skips providers without api_key', () => {
    expect(
      buildLlmKeysFromProviders([
        { ...sampleProviders[0], api_key: null, configured: false },
      ]),
    ).toEqual({});
  });
});

describe('buildProviderEnvVars', () => {
  it('mirrors api_key into configured env names', () => {
    expect(buildProviderEnvVars(sampleProviders)).toEqual({
      NVIDIA_API_KEY: 'nvapi-test-key',
    });
  });
});

describe('buildContextRefreshPayload', () => {
  it('includes paths and kind', () => {
    expect(
      buildContextRefreshPayload({
        creatorId: 'c1',
        sessionId: '999',
        threadId: 't1',
        sessionKind: 'vod',
        transcriptPath: 'creators/x/videos/999.transcript.json',
        summaryPath: null,
        contextMode: 'transcript',
      }),
    ).toEqual({
      creatorId: 'c1',
      sessionId: '999',
      threadId: 't1',
      sessionKind: 'vod',
      transcriptPath: 'creators/x/videos/999.transcript.json',
      summaryPath: null,
      contextMode: 'transcript',
    });
  });
});
