import { describe, expect, it } from 'vitest';
import { selectionFromSessionRow, type SessionListItem } from './transcriptSelection';

describe('selectionFromSessionRow', () => {
  it('maps live session row', () => {
    const row: SessionListItem = { kind: 'live', item_id: 'uuid-1', has_transcript: true };
    expect(selectionFromSessionRow(row)).toEqual({
      mode: 'history',
      kind: 'live',
      itemId: 'uuid-1',
      hasTranscript: true,
      hasSummary: false,
      transcriptPath: null,
      summaryPath: null,
    });
  });

  it('maps vod session row with sidecars', () => {
    const row: SessionListItem = {
      kind: 'vod',
      item_id: 'aweme-1',
      has_transcript: false,
      has_summary: true,
      transcript_path: 'creators/x/videos/a.transcript.json',
      summary_path: 'creators/x/videos/a.summary.md',
    };
    expect(selectionFromSessionRow(row)).toEqual({
      mode: 'history',
      kind: 'vod',
      itemId: 'aweme-1',
      hasTranscript: false,
      hasSummary: true,
      transcriptPath: 'creators/x/videos/a.transcript.json',
      summaryPath: 'creators/x/videos/a.summary.md',
    });
  });
});
