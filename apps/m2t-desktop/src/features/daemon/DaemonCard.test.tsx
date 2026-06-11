import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { RuntimeStatus } from '../../lib/types';
import { DaemonCard, buildDaemonStats, formatHealthReason } from './DaemonCard';

vi.mock('../../lib/api', () => ({
  apiGet: vi.fn().mockResolvedValue({
    ok: true,
    monitor_tasks: [],
    post_process: [],
    stale_creators: [],
  }),
  apiPost: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

vi.mock('../runtime/RuntimeContext', () => ({
  useRuntime: vi.fn(),
}));

import { useRuntime } from '../runtime/RuntimeContext';

const baseRuntime: RuntimeStatus = {
  ok: true,
  health: 'healthy',
  health_reasons: [],
  managed_by: 'embedded',
  daemon: {
    running: true,
    pid: 42,
    lock_pid: 42,
    started_at: null,
    last_tick_at: '2026-06-05T00:00:00Z',
    tick_age_sec: 2,
    live_poll_interval_sec: 20,
  },
  recordings: { active_count: 1, items: [] },
  queues: {
    post_process: { pending: 0, running: 0, max_workers: 2 },
    monitor_tasks: {
      pending: 0,
      running: 2,
      failed_total: 50,
      failed_recent_24h: 2,
      dlq: 50,
    },
  },
  observability: { snapshots_stale_count: 0, monitored_creators: 3 },
  log_path: 'data/monitor-watch.log',
};

describe('formatHealthReason', () => {
  it('localizes known reasons in plain language', () => {
    expect(formatHealthReason('live tick stale')).toContain('心跳超时');
    expect(formatHealthReason('3 monitor task failures in 24h')).toContain('近 24 小时');
  });
});

describe('buildDaemonStats', () => {
  it('shows queue stats and managed_by', () => {
    const stats = buildDaemonStats(baseRuntime);
    expect(stats.find((s) => s.label === '运行方式')?.value).toContain('Desktop 内嵌');
    expect(stats.find((s) => s.label === '录后处理')?.value).toBe('0 排队 · 0 进行中');
    expect(stats.find((s) => s.label === '作品任务')?.value).toBe('0 排队 · 2 进行中');
    expect(stats.find((s) => s.label === '直播检测')).toBeUndefined();
    expect(stats.find((s) => s.label === '正在录制')).toBeUndefined();
    expect(stats.find((s) => s.label === '近 24h 失败')).toBeUndefined();
    expect(stats.find((s) => s.label === '状态过期')).toBeUndefined();
  });
});

describe('DaemonCard', () => {
  it('renders healthy state', () => {
    vi.mocked(useRuntime).mockReturnValue({
      runtime: baseRuntime,
      loading: false,
      fetchError: null,
      connected: true,
      refresh: async () => {},
      startRuntime: async () => {},
      stopRuntime: async () => {},
      restartRuntime: async () => {},
      takeoverRuntime: async () => {},
      handoffRuntime: async () => {},
    });
    render(<DaemonCard />);
    expect(screen.getByText('后台监控')).toBeInTheDocument();
    expect(screen.queryByText('正在自动检测直播并同步作品')).not.toBeInTheDocument();
    expect(screen.getByLabelText(/后台监控：运行正常/)).toBeInTheDocument();
  });

  it('renders degraded state without inline alert list', () => {
    vi.mocked(useRuntime).mockReturnValue({
      runtime: {
        ...baseRuntime,
        health: 'degraded',
        health_reasons: ['live tick stale'],
        daemon: { ...baseRuntime.daemon, running: true },
      },
      loading: false,
      fetchError: null,
      connected: true,
      refresh: async () => {},
      startRuntime: async () => {},
      stopRuntime: async () => {},
      restartRuntime: async () => {},
      takeoverRuntime: async () => {},
      handoffRuntime: async () => {},
    });
    render(<DaemonCard />);
    expect(screen.getByText('后台监控')).toBeInTheDocument();
    expect(screen.queryByText('需要关注')).not.toBeInTheDocument();
    expect(screen.getByLabelText(/后台监控：异常/)).toBeInTheDocument();
    expect(screen.queryByText(/心跳超时/)).not.toBeInTheDocument();
    expect(screen.queryByText('清理卡住任务')).not.toBeInTheDocument();
    expect(screen.getByLabelText('任务详情')).toBeInTheDocument();
  });

  it('shows external controls when terminal daemon', () => {
    vi.mocked(useRuntime).mockReturnValue({
      runtime: {
        ...baseRuntime,
        managed_by: 'external',
        daemon: { ...baseRuntime.daemon, running: true, pid: 999 },
      },
      loading: false,
      fetchError: null,
      connected: true,
      refresh: async () => {},
      startRuntime: async () => {},
      stopRuntime: async () => {},
      restartRuntime: async () => {},
      takeoverRuntime: async () => {},
      handoffRuntime: async () => {},
    });
    render(<DaemonCard />);
    expect(screen.getByRole('button', { name: '改用 Desktop' })).toBeInTheDocument();
    expect(screen.getByText(/终端守护进程/)).toBeInTheDocument();
  });

  it('renders stopped state', () => {
    vi.mocked(useRuntime).mockReturnValue({
      runtime: {
        ...baseRuntime,
        health: 'stopped',
        health_reasons: ['monitor not running'],
        managed_by: 'none',
        daemon: { ...baseRuntime.daemon, running: false, pid: null },
      },
      loading: false,
      fetchError: null,
      connected: true,
      refresh: async () => {},
      startRuntime: async () => {},
      stopRuntime: async () => {},
      restartRuntime: async () => {},
      takeoverRuntime: async () => {},
      handoffRuntime: async () => {},
    });
    render(<DaemonCard />);
    expect(screen.getByText('后台监控')).toBeInTheDocument();
    expect(screen.queryByText('已停止')).not.toBeInTheDocument();
    expect(screen.getByLabelText(/后台监控：已停止/)).toBeInTheDocument();
  });
});
