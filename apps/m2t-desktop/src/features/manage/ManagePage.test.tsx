import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ManagePage } from './ManagePage';

const apiMocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiDelete: vi.fn(),
  apiPatch: vi.fn(),
  apiPost: vi.fn(),
}));

vi.mock('../../lib/api', () => ({
  ...apiMocks,
  getApiBaseUrl: vi.fn().mockResolvedValue('http://127.0.0.1:8765'),
  creatorAvatarUrl: vi.fn(async (id: string, version?: string | null) => {
    const q = version ? `?v=${encodeURIComponent(version)}` : '';
    return `http://127.0.0.1:8765/api/creators/${id}/avatar${q}`;
  }),
}));

vi.mock('../creators/CreatorsContext', () => ({
  useCreators: () => ({ refresh: vi.fn() }),
}));

const sampleCreator = {
  id: 'creator-1',
  platform: 'douyin',
  sec_uid: 'sec_1',
  display_name: '测试博主',
  unique_id: 'test_user',
  monitor_enabled: true,
  auto_record_override: 'inherit',
  status_light: 'gray',
  status_abbr: '—',
  profile_stale: false,
  profile_url: null,
  is_live: false,
  badge: '',
  badge_class: '',
  avatar_url: 'https://example.com/avatar.jpg',
  signature: '这是简介',
  follower_count: 50_000,
  profile_synced_at: '2026-06-05T12:00:00+00:00',
  active_session_id: null,
};

describe('ManagePage remove creator', () => {
  beforeEach(() => {
    apiMocks.apiGet.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/creators')) {
        return { ok: true, creators: [sampleCreator] };
      }
      if (path === '/api/config') {
        return { config: { autoRecord: true } };
      }
      throw new Error(`unexpected GET ${path}`);
    });
    apiMocks.apiDelete.mockResolvedValue({ ok: true });
    apiMocks.apiPatch.mockResolvedValue({ ok: true });
    apiMocks.apiPost.mockResolvedValue({ ok: true });
  });

  it('shows synced profile in drawer', async () => {
    render(<ManagePage />);

    expect(await screen.findByRole('region', { name: '博主资料' })).toBeTruthy();
    expect(screen.getByText('这是简介')).toBeTruthy();
    expect(screen.getByText(/粉丝 5万/)).toBeTruthy();
    expect(screen.getByText(/同步于/)).toBeTruthy();
  });

  it('opens confirm dialog and removes creator on confirm', async () => {
    const user = userEvent.setup();
    render(<ManagePage />);

    await screen.findByRole('button', { name: '移除博主' });
    await user.click(screen.getByRole('button', { name: '移除博主' }));

    expect(screen.getByRole('alertdialog', { name: '移除博主' })).toBeTruthy();
    expect(screen.getByText(/确定移除 测试博主/)).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '移除' }));

    await waitFor(() => {
      expect(apiMocks.apiDelete).toHaveBeenCalledWith('/api/creators/creator-1');
    });
  });
});
