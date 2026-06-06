import { describe, expect, it } from 'vitest';
import { selectionFromSessionRow, type SessionListItem } from './transcriptSelection';

describe('selectionFromSessionRow', () => {
  it('maps live row to history selection', () => {
    const row: SessionListItem = { kind: 'live', item_id: 'uuid-1', has_transcript: true };
    expect(selectionFromSessionRow(row)).toEqual({
      mode: 'history',
      kind: 'live',
      itemId: 'uuid-1',
    });
  });

  it('maps vod row to history selection', () => {
    const row: SessionListItem = { kind: 'vod', item_id: 'aweme-1', has_transcript: false };
    expect(selectionFromSessionRow(row)).toEqual({
      mode: 'history',
      kind: 'vod',
      itemId: 'aweme-1',
    });
  });
});
