import { describe, expect, it } from 'vitest';
import type { LiveSessionSummary } from '../../lib/types';
import {
  expandSessionToMentionRows,
  filterMentionRows,
  mentionRowToAttachment,
  parseMentionAtCaret,
  removeMentionSegment,
} from './mentionDocuments';

const baseSession = (overrides: Partial<LiveSessionSummary> = {}): LiveSessionSummary => ({
  kind: 'live',
  item_id: 'sess-1',
  session_id: 'sess-1',
  aweme_id: null,
  title: null,
  creator_id: 'c1',
  started_at: '2026-06-02T13:04:00Z',
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
  has_transcript: true,
  has_summary: true,
  media_available: true,
  transcript_path: 'creators/x/live/a.transcript.json',
  summary_path: 'creators/x/live/a.summary.md',
  ...overrides,
});

describe('mentionDocuments', () => {
  it('expandSessionToMentionRows splits transcript and summary', () => {
    const rows = expandSessionToMentionRows(baseSession(), '博主A');
    expect(rows).toHaveLength(2);
    expect(rows.map((r) => r.docType)).toEqual(['transcript', 'summary']);
  });

  it('filterMentionRows matches creator name', () => {
    const rows = expandSessionToMentionRows(baseSession(), '博主A');
    expect(filterMentionRows(rows, '博主A')).toHaveLength(2);
    expect(filterMentionRows(rows, '不存在')).toHaveLength(0);
  });

  it('mentionRowToAttachment uses mention source', () => {
    const [row] = expandSessionToMentionRows(baseSession(), '博主A');
    expect(mentionRowToAttachment(row!).source).toBe('mention');
  });

  it('parseMentionAtCaret detects @query before caret', () => {
    expect(parseMentionAtCaret('hello @abc world', 10)).toEqual({ start: 6, query: 'abc' });
    expect(parseMentionAtCaret('hello @abc world', 7)).toEqual({ start: 6, query: '' });
    expect(parseMentionAtCaret('no mention', 10)).toBeNull();
  });

  it('removeMentionSegment strips @token', () => {
    expect(removeMentionSegment('前缀 @tok 后缀', 3, 7)).toBe('前缀  后缀');
  });
});
