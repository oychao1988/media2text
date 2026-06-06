import { describe, expect, it } from 'vitest';
import { groupThreadsByAgent, threadAgentId, filterThreadsByQuery } from './agentGroups';
import type { ThreadRow } from './types';

function thread(id: string, creatorId: string | null, title: string): ThreadRow {
  return {
    id,
    creator_id: creatorId,
    session_id: null,
    title,
    provider_name: null,
    model: 'auto',
    updated_at: new Date().toISOString(),
  };
}

describe('agentGroups', () => {
  it('threadAgentId uses global for null creator', () => {
    expect(threadAgentId({ creator_id: null })).toBe('global');
    expect(threadAgentId({ creator_id: 'c1' })).toBe('c1');
  });

  it('groupThreadsByAgent puts global first then creators in order', () => {
    const threads = [
      thread('t1', 'c2', 'B'),
      thread('t2', null, 'G'),
      thread('t3', 'c1', 'A'),
    ];
    const creators = [
      { id: 'c1', display_name: 'Creator One' },
      { id: 'c2', display_name: 'Creator Two' },
    ];
    const groups = groupThreadsByAgent(threads, creators);
    expect(groups.map((g) => g.agentId)).toEqual(['global', 'c1', 'c2']);
    expect(groups[0]!.profile.name).toBe('灵犀');
  });

  it('hides empty agent groups', () => {
    const groups = groupThreadsByAgent([], []);
    expect(groups).toEqual([]);
  });

  it('filterThreadsByQuery matches title case-insensitively', () => {
    const rows = [thread('1', null, 'Market Recap')];
    expect(filterThreadsByQuery(rows, 'market')).toHaveLength(1);
    expect(filterThreadsByQuery(rows, 'other')).toHaveLength(0);
  });
});
