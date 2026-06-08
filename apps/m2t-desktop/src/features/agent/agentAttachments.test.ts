import { describe, expect, it } from 'vitest';
import {
  attachmentsFromSessionOffer,
  dedupeByPath,
  filterByContextMode,
  legacyBindingToAttachments,
} from './agentAttachments';
import type { ContextAttachment } from './contextAttachment';

const baseAttachment = (overrides: Partial<ContextAttachment> = {}): ContextAttachment => ({
  id: 'transcript:creators/a/live/x.transcript.json',
  docType: 'transcript',
  path: 'creators/a/live/x.transcript.json',
  label: '直播场次',
  creatorId: 'c1',
  creatorName: '博主A',
  sessionKind: 'live',
  itemId: 'sess-1',
  source: 'session',
  ...overrides,
});

describe('agentAttachments', () => {
  it('dedupeByPath keeps first occurrence per path', () => {
    const a = baseAttachment();
    const b = baseAttachment({
      id: 'summary:creators/a/live/x.transcript.json',
      docType: 'summary',
      source: 'mention',
    });
    expect(dedupeByPath([a, b])).toHaveLength(1);
    expect(dedupeByPath([a, b])[0]?.source).toBe('session');
  });

  it('legacyBindingToAttachments migrates legacy paths', () => {
    const items = legacyBindingToAttachments({
      transcriptPath: 'creators/x/live/a.transcript.json',
      summaryPath: 'creators/x/live/a.summary.md',
      creatorId: 'c1',
      creatorName: '博主',
      sessionKind: 'live',
      itemId: 'live-1',
    });
    expect(items).toHaveLength(2);
    expect(items.map((i) => i.docType)).toEqual(['transcript', 'summary']);
  });

  it('legacyBindingToAttachments prefers explicit attachments array', () => {
    const explicit = [baseAttachment({ path: 'creators/z/custom.json' })];
    const items = legacyBindingToAttachments({
      attachments: explicit,
      transcriptPath: 'ignored.json',
    });
    expect(items).toEqual(explicit);
  });

  it('filterByContextMode filters by docType', () => {
    const items = [
      baseAttachment(),
      baseAttachment({
        id: 'summary:creators/a/live/x.summary.md',
        docType: 'summary',
        path: 'creators/a/live/x.summary.md',
      }),
    ];
    expect(filterByContextMode(items, 'both')).toHaveLength(2);
    expect(filterByContextMode(items, 'transcript')).toHaveLength(1);
    expect(filterByContextMode(items, 'summary')).toHaveLength(1);
  });

  it('attachmentsFromSessionOffer builds transcript and summary chips', () => {
    const items = attachmentsFromSessionOffer({
      sessionId: 'sess-1',
      sessionKind: 'vod',
      creatorId: 'c1',
      creatorName: '博主A',
      itemId: 'aweme-1',
      label: '作品标题',
      hasTranscript: true,
      hasSummary: true,
      transcriptPath: 'creators/a/videos/1.transcript.json',
      summaryPath: 'creators/a/videos/1.summary.md',
    });
    expect(items).toHaveLength(2);
    expect(items.every((i) => i.source === 'session')).toBe(true);
  });
});
