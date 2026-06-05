import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CreatorHoverPopover } from './CreatorHoverPopover';
import type { Creator } from '../../lib/types';

vi.mock('../../lib/api', () => ({
  getApiBaseUrl: vi.fn().mockResolvedValue('http://127.0.0.1:8765'),
  creatorAvatarUrl: vi.fn(async (id: string) => `http://127.0.0.1:8765/api/creators/${id}/avatar`),
}));

const creator: Creator = {
  id: 'creator-1',
  platform: 'douyin',
  sec_uid: 'sec_1',
  display_name: '测试博主',
  unique_id: 'test_user',
  monitor_enabled: true,
  profile_stale: false,
  auto_record_override: 'inherit',
  status_light: 'red',
  is_live: true,
  badge: '',
  badge_class: '',
  status_abbr: '播',
  profile_url: null,
  avatar_url: 'https://example.com/a.jpg',
  signature: '直播简介',
  follower_count: 12_300,
  profile_synced_at: '2026-06-05T12:00:00+00:00',
  active_session_id: null,
  live_snapshot: { is_live: true, room_id: 'r1', title: '今晚聊天', checked_at: null },
};

describe('CreatorHoverPopover', () => {
  it('shows creator profile tooltip on hover', async () => {
    const user = userEvent.setup();
    render(
      <CreatorHoverPopover creator={creator}>
        <button type="button">博主</button>
      </CreatorHoverPopover>,
    );

    await user.hover(screen.getByRole('button', { name: '博主' }));

    await waitFor(
      () => {
        expect(screen.getByRole('tooltip')).toBeTruthy();
        expect(screen.getByText('测试博主')).toBeTruthy();
        expect(screen.getByText('直播简介')).toBeTruthy();
        expect(screen.getByText('今晚聊天')).toBeTruthy();
        expect(screen.getByText(/粉丝 1.2万/)).toBeTruthy();
      },
      { timeout: 800 },
    );
  });
});
