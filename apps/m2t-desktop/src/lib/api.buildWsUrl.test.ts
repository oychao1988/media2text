import { beforeEach, describe, expect, it, vi } from 'vitest';
import { buildWsUrl, resetApiBaseUrlCache } from './api';
import * as tauriBridge from './tauriBridge';

vi.mock('./toast', () => ({
  showToast: vi.fn(),
}));

describe('buildWsUrl', () => {
  beforeEach(() => {
    resetApiBaseUrlCache();
    vi.spyOn(tauriBridge, 'resolveApiBaseUrl').mockResolvedValue('http://127.0.0.1:8765');
  });

  it('preserves query string for agent stream threadId', async () => {
    const url = await buildWsUrl('/api/agent/stream?threadId=thread-abc');
    expect(url).toBe('ws://127.0.0.1:8765/api/agent/stream?threadId=thread-abc');
  });

  it('converts http base to ws without encoding ? in pathname', async () => {
    const url = await buildWsUrl('/api/events');
    expect(url).toBe('ws://127.0.0.1:8765/api/events');
  });
});
