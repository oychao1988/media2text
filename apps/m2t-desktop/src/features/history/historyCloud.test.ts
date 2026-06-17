import { describe, expect, it } from 'vitest';
import { mergeSessionEnrichInfo, sessionCloudKey } from './historyCloud';
import type { LiveSessionSummary } from '../../lib/types';

const baseSession: LiveSessionSummary = {
  kind: 'live',
  item_id: 's1',
  session_id: 's1',
  aweme_id: null,
  title: null,
  creator_id: 'c1',
  started_at: null,
  ended_at: null,
  status: 'completed',
  local_path: null,
  temp_path: null,
  media_path: null,
  pipeline_mode: null,
  transcribe_status: null,
  cloud_upload_status: null,
  cloud_file_id: null,
  cloud_relative_path: null,
  cloud_available: false,
  has_transcript: false,
  has_summary: false,
  media_available: false,
  transcript_path: null,
  summary_path: null,
};

describe('historyCloud', () => {
  it('builds stable session keys', () => {
    expect(sessionCloudKey({ kind: 'live', item_id: 'abc' })).toBe('live:abc');
    expect(sessionCloudKey({ kind: 'vod', item_id: 'aweme1' })).toBe('vod:aweme1');
  });

  it('merges cloud fields into matching sessions', () => {
    const merged = mergeSessionEnrichInfo([baseSession], {
      'live:s1': {
        cloud_upload_status: 'done',
        cloud_file_id: 'file-1',
        cloud_relative_path: 'douyin/live/a.mp4',
        cloud_available: true,
      },
    });
    expect(merged[0].cloud_available).toBe(true);
    expect(merged[0].cloud_file_id).toBe('file-1');
  });
});
