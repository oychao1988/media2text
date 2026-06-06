import { describe, expect, it, vi } from 'vitest';
import { applyRefreshPayload, hydrateContextFromApi, type RuntimeContext } from './context.js';

describe('applyRefreshPayload', () => {
  it('sets paths and skips session GET when transcriptPath provided', async () => {
    const ctx: RuntimeContext = {
      apiBaseUrl: 'http://127.0.0.1:8765',
      workspace: './data',
      creatorId: 'c1',
      sessionId: '999',
      threadId: 't1',
      creatorName: null,
      creatorPlatform: null,
      sessionStartedAt: null,
      transcriptPath: null,
      summaryPath: null,
    };
    applyRefreshPayload(ctx, {
      creatorId: 'c1',
      sessionId: '999',
      sessionKind: 'vod',
      transcriptPath: 'creators/x/videos/999.transcript.json',
      summaryPath: 'creators/x/videos/999.summary.md',
    });
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    await hydrateContextFromApi(ctx);
    expect(ctx.transcriptPath).toBe('creators/x/videos/999.transcript.json');
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining('/api/sessions/999'),
      expect.anything(),
    );
    vi.unstubAllGlobals();
  });
});
