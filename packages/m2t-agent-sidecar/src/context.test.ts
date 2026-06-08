import { describe, expect, it, vi } from 'vitest';
import {
  applyRefreshPayload,
  buildSystemPrompt,
  hydrateContextFromApi,
  type RuntimeContext,
} from './context.js';

const baseCtx = (): RuntimeContext => ({
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
  contextMode: 'both',
  attachments: [],
});

describe('applyRefreshPayload', () => {
  it('sets paths and skips session GET when transcriptPath provided', async () => {
    const ctx = baseCtx();
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

  it('persists attachments to env and ctx', () => {
    const ctx = baseCtx();
    applyRefreshPayload(ctx, {
      attachments: [
        {
          id: 'summary:creators/x/live/a.summary.md',
          docType: 'summary',
          path: 'creators/x/live/a.summary.md',
          label: '2026-06-02 直播 · 摘要',
          creatorId: 'c2',
          creatorName: '博主B',
          sessionKind: 'live',
          itemId: 'sess-2',
          source: 'mention',
        },
      ],
      contextMode: 'summary',
    });
    expect(ctx.attachments).toHaveLength(1);
    expect(process.env.M2T_ATTACHMENTS).toContain('creators/x/live/a.summary.md');
    expect(process.env.M2T_CONTEXT_MODE).toBe('summary');
  });
});

describe('buildSystemPrompt', () => {
  it('includes filtered attachments block', () => {
    const ctx = baseCtx();
    ctx.attachments = [
      {
        id: 't1',
        docType: 'transcript',
        path: 'creators/a/live/t.transcript.json',
        label: '转写',
        creatorId: 'c1',
        creatorName: '博主A',
        sessionKind: 'live',
        itemId: 's1',
      },
      {
        id: 's1',
        docType: 'summary',
        path: 'creators/a/live/t.summary.md',
        label: '摘要',
        creatorId: 'c1',
        creatorName: '博主A',
        sessionKind: 'live',
        itemId: 's1',
      },
    ];
    ctx.contextMode = 'transcript';
    const prompt = buildSystemPrompt(ctx);
    expect(prompt).toContain('## 附加文档');
    expect(prompt).toContain('creators/a/live/t.transcript.json');
    expect(prompt).not.toContain('t.summary.md');
  });
});
