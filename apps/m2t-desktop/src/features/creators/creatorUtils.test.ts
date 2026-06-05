import { describe, expect, it } from 'vitest';
import {
  creatorLiveRank,
  formatFollowerCount,
  formatProfileSyncedAt,
  sortCreatorsLiveFirst,
} from './creatorUtils';
import type { Creator } from '../../lib/types';

const base = (overrides: Partial<Creator>): Creator =>
  ({
    id: 'c1',
    platform: 'douyin',
    sec_uid: 's',
    display_name: 'A',
    unique_id: null,
    profile_url: null,
    monitor_enabled: true,
    profile_stale: false,
    auto_record_override: 'inherit',
    status_light: 'gray',
    is_live: false,
    badge: '',
    badge_class: '',
    status_abbr: '—',
    avatar_url: null,
    signature: null,
    follower_count: null,
    profile_synced_at: null,
    active_session_id: null,
    ...overrides,
  }) as Creator;

describe('sortCreatorsLiveFirst', () => {
  it('pins live creators above offline', () => {
    const offline = base({ id: 'off', display_name: '离线' });
    const live = base({ id: 'live', display_name: '在播', is_live: true, status_light: 'red' });
    const recording = base({ id: 'rec', display_name: '录制', status_light: 'green' });
    expect(sortCreatorsLiveFirst([offline, live, recording]).map((c) => c.id)).toEqual([
      'rec',
      'live',
      'off',
    ]);
  });

  it('ranks recording above live-not-recording', () => {
    expect(creatorLiveRank(base({ status_light: 'green' }))).toBeGreaterThan(
      creatorLiveRank(base({ is_live: true, status_light: 'red' })),
    );
  });
});

describe('creatorUtils profile formatting', () => {
  it('formats follower counts', () => {
    expect(formatFollowerCount(null)).toBeNull();
    expect(formatFollowerCount(999)).toBe('999');
    expect(formatFollowerCount(12_300)).toBe('1.2万');
    expect(formatFollowerCount(100_000)).toBe('10万');
  });

  it('formats profile sync time', () => {
    expect(formatProfileSyncedAt('2026-06-05T12:00:00+00:00')).toMatch(/6\/5/);
    expect(formatProfileSyncedAt('invalid')).toBeNull();
  });
});
