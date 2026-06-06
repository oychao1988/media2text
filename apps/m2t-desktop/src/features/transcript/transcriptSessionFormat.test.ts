import { describe, expect, it } from 'vitest';
import { formatSessionOptionMeta, sessionOptionTitle } from './transcriptSessionFormat';
import type { SessionListItem } from './transcriptSelection';

describe('transcriptSessionFormat', () => {
  it('formats meta from started_at', () => {
    const meta = formatSessionOptionMeta('2026-06-02T12:03:00.000Z');
    expect(meta).toMatch(/06-02/);
    expect(meta).toMatch(/\d{2}:\d{2}/);
  });

  it('uses vod title and strips live date prefix', () => {
    const vod: SessionListItem = {
      kind: 'vod',
      item_id: 'a1',
      has_transcript: true,
      title: '今晚复盘',
    };
    expect(sessionOptionTitle(vod)).toBe('今晚复盘');

    const live: SessionListItem = {
      kind: 'live',
      item_id: 's1',
      has_transcript: true,
      display_label: '2026-06-02 20:03 直播',
    };
    expect(sessionOptionTitle(live)).toBe('直播');
  });
});
