import { describe, expect, it } from 'vitest';
import { buildActivatePayload } from './agentContext';

describe('buildActivatePayload', () => {
  it('includes paths and kind', () => {
    expect(
      buildActivatePayload({
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
      sessionKind: 'vod',
      transcriptPath: 'creators/x/videos/999.transcript.json',
      summaryPath: null,
      contextMode: 'transcript',
    });
  });

  it('clears session when sessionId is null', () => {
    expect(
      buildActivatePayload({
        creatorId: 'c1',
        sessionId: null,
        contextMode: 'both',
      }),
    ).toEqual({
      creatorId: 'c1',
      clearSession: true,
      contextMode: 'both',
    });
  });
});
