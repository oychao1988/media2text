import { describe, expect, it } from 'vitest';
import {
  filterThreadsByQuery,
  groupThreadByUpdatedAt,
  groupThreads,
  THREAD_GROUP_LABELS,
} from './threadGroups';
import type { ThreadRow } from './types';

function thread(id: string, title: string, updatedAt: string): ThreadRow {
  return {
    id,
    creator_id: 'c1',
    session_id: null,
    title,
    provider_name: null,
    model: 'auto',
    updated_at: updatedAt,
  };
}

describe('threadGroups', () => {
  it('labels four time groups (A4)', () => {
    expect(THREAD_GROUP_LABELS.today).toBe('TODAY');
    expect(THREAD_GROUP_LABELS.yesterday).toBe('YESTERDAY');
    expect(THREAD_GROUP_LABELS.week).toBe('LAST 7 DAYS');
    expect(THREAD_GROUP_LABELS.month).toBe('LAST 30 DAYS');
  });

  it('groups by updated_at day buckets', () => {
    const now = new Date();
    const todayIso = now.toISOString();
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    expect(groupThreadByUpdatedAt(todayIso)).toBe('today');
    expect(groupThreadByUpdatedAt(yesterday.toISOString())).toBe('yesterday');
  });

  it('filterThreadsByQuery matches title substring', () => {
    const grouped = groupThreads([
      thread('1', 'Alpha notes', '2026-06-06T10:00:00Z'),
      thread('2', 'Beta recap', '2026-06-05T10:00:00Z'),
    ]);
    expect(filterThreadsByQuery(grouped, 'alpha')).toHaveLength(1);
    expect(filterThreadsByQuery(grouped, '')).toHaveLength(2);
  });
});
