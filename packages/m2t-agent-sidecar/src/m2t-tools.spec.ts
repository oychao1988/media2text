import { afterEach, describe, expect, it, vi } from 'vitest';
import { createInitialContext } from './context.js';
import { M2tApiClient } from './m2t-api.js';

describe('M2tApiClient', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('GET live status returns ok payload', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({ ok: true, running: true }, { status: 200 }),
      ),
    );

    const client = new M2tApiClient({ baseUrl: 'http://127.0.0.1:8765' });
    const result = await client.request('GET', '/api/live/status');
    expect(result.ok).toBe(true);
    expect((result.data as { ok?: boolean; running?: boolean }).ok).toBe(true);
    expect((result.data as { running?: boolean }).running).toBe(true);
  });

  it('maps HTTP errors to tool error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({ detail: 'manifest not found' }, { status: 404 }),
      ),
    );

    const client = new M2tApiClient({ baseUrl: 'http://127.0.0.1:8765' });
    const result = await client.request('GET', '/api/creators/missing/manifest');
    expect(result.ok).toBe(false);
    expect(result.error?.code).toBe('404');
  });
});

describe('buildSystemPrompt', () => {
  it('includes compliance disclaimer', async () => {
    const { buildSystemPrompt } = await import('./context.js');
    const ctx = createInitialContext();
    const prompt = buildSystemPrompt(ctx);
    expect(prompt).toContain('个人研究档案');
    expect(prompt).toContain('不构成投资咨询');
  });
});
