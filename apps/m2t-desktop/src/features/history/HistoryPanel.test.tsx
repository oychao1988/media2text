import { render, screen, waitFor, act } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { HistoryPanel } from './HistoryPanel';

const apiGet = vi.fn();

vi.mock('../../lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGet(...args),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
  getApiBaseUrl: vi.fn().mockResolvedValue('http://127.0.0.1:8765'),
  ApiError: class ApiError extends Error {},
}));

describe('HistoryPanel', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    apiGet.mockReset();
    apiGet.mockImplementation((path: string) => {
      if (path.includes('/sessions/cloud')) {
        return Promise.resolve({ ok: true, items: {} });
      }
      if (path.includes('/sessions?')) {
        return Promise.resolve({ ok: true, sessions: [], live_groups: [] });
      }
      return Promise.resolve({ ok: true, sessions: [], live_groups: [] });
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('loads cloud info after sessions list', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path.includes('/sessions/cloud')) {
        return Promise.resolve({
          ok: true,
          items: {
            'live:a1': {
              cloud_upload_status: 'done',
              cloud_file_id: 'f1',
              cloud_relative_path: 'x/y.mp4',
              cloud_available: true,
            },
          },
        });
      }
      if (path.includes('/sessions?')) {
        return Promise.resolve({
          ok: true,
          sessions: [
            {
              kind: 'live',
              item_id: 'a1',
              started_at: '2026-06-01T10:00:00+00:00',
              ended_at: '2026-06-01T11:00:00+00:00',
              media_available: true,
              cloud_upload_status: null,
              cloud_available: false,
            },
          ],
          live_groups: [],
        });
      }
      return Promise.resolve({ ok: true, sessions: [], live_groups: [] });
    });

    render(<HistoryPanel creatorId="a" active onSessionSelect={() => {}} />);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });

    await waitFor(() => {
      expect(screen.getByText('☁ 已备份')).toBeInTheDocument();
    });
    expect(apiGet.mock.calls.some(([path]) => String(path).includes('include_cloud=false'))).toBe(
      true,
    );
    expect(apiGet.mock.calls.some(([path]) => String(path).includes('/sessions/cloud'))).toBe(
      true,
    );
  });

  it('clears stale rows when switching creators before fetch completes', async () => {
    let resolveB: ((value: unknown) => void) | undefined;
    apiGet.mockImplementation((path: string) => {
      if (path.includes('/creators/a/sessions')) {
        return Promise.resolve({
          ok: true,
          sessions: [{ kind: 'live', item_id: 'a1', started_at: '2026-06-01T10:00:00+00:00' }],
          live_groups: [],
        });
      }
      if (path.includes('/creators/b/sessions')) {
        return new Promise((resolve) => {
          resolveB = resolve;
        });
      }
      return Promise.resolve({ ok: true, sessions: [], live_groups: [] });
    });

    const { rerender } = render(
      <HistoryPanel creatorId="a" active onSessionSelect={() => {}} />,
    );

    await waitFor(() => {
      expect(screen.getByText(/2026-06-01/)).toBeInTheDocument();
    });

    rerender(<HistoryPanel creatorId="b" active onSessionSelect={() => {}} />);

    expect(screen.queryByText(/2026-06-01/)).not.toBeInTheDocument();
    expect(screen.getByText('加载历史…')).toBeInTheDocument();

    resolveB?.({
      ok: true,
      sessions: [{ kind: 'live', item_id: 'b1', started_at: '2026-06-02T12:00:00+00:00' }],
      live_groups: [],
    });

    await waitFor(() => {
      expect(screen.getByText(/2026-06-02/)).toBeInTheDocument();
    });
  });

  it('clears loading after rapid creator switches', async () => {
    apiGet.mockImplementation((path: string) => {
      const p = String(path);
      if (p.includes('/creators/slow/sessions?')) {
        return new Promise(() => {});
      }
      if (p.includes('/creators/fast/sessions?')) {
        return Promise.resolve({
          ok: true,
          sessions: [
            {
              kind: 'live',
              item_id: 'f1',
              started_at: '2026-06-03T08:00:00+00:00',
              ended_at: '2026-06-03T09:00:00+00:00',
            },
          ],
          live_groups: [],
        });
      }
      if (p.includes('/sessions/cloud')) {
        return Promise.resolve({ ok: true, items: {} });
      }
      return Promise.resolve({ ok: true, sessions: [], live_groups: [] });
    });

    const { rerender } = render(
      <HistoryPanel creatorId="slow" active onSessionSelect={() => {}} />,
    );
    expect(screen.getByText('加载历史…')).toBeInTheDocument();

    rerender(<HistoryPanel creatorId="fast" active onSessionSelect={() => {}} />);

    await waitFor(() => {
      expect(screen.queryByText('加载历史…')).not.toBeInTheDocument();
      expect(screen.getByText(/2026-06-03/)).toBeInTheDocument();
    });
  });

  it('does not enrich abandoned creators when switching quickly', async () => {
    let cloudCalls = 0;
    apiGet.mockImplementation((path: string) => {
      const p = String(path);
      if (p.includes('/sessions/cloud')) {
        cloudCalls += 1;
        return Promise.resolve({ ok: true, items: {} });
      }
      if (p.includes('/creators/a/sessions?')) {
        return Promise.resolve({
          ok: true,
          sessions: [{ kind: 'live', item_id: 'a1', started_at: '2026-06-01T10:00:00+00:00' }],
          live_groups: [],
        });
      }
      if (p.includes('/creators/b/sessions?')) {
        return Promise.resolve({
          ok: true,
          sessions: [{ kind: 'live', item_id: 'b1', started_at: '2026-06-02T12:00:00+00:00' }],
          live_groups: [],
        });
      }
      return Promise.resolve({ ok: true, sessions: [], live_groups: [] });
    });

    const { rerender } = render(
      <HistoryPanel creatorId="a" active onSessionSelect={() => {}} />,
    );
    rerender(<HistoryPanel creatorId="b" active onSessionSelect={() => {}} />);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(cloudCalls).toBeLessThanOrEqual(1);
  });

  it('does not fetch when inactive', async () => {
    render(<HistoryPanel creatorId="a" active={false} onSessionSelect={() => {}} />);
    await waitFor(() => {
      expect(apiGet).not.toHaveBeenCalled();
    });
  });
});
