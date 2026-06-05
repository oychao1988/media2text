import { describe, expect, it } from 'vitest';
import { mergeRuntimePatch } from './runtimeMerge';
import type { RuntimeStatus } from '../../lib/types';

const base: RuntimeStatus = {
  ok: true,
  health: 'healthy',
  health_reasons: [],
  managed_by: 'embedded',
  daemon: {
    running: true,
    pid: 1,
    lock_pid: 1,
    started_at: null,
    last_tick_at: '2026-06-05T00:00:00Z',
    tick_age_sec: 2,
    live_poll_interval_sec: 20,
  },
  recordings: { active_count: 0, items: [] },
  queues: {
    post_process: { pending: 0, running: 0, max_workers: 2 },
    monitor_tasks: {
      pending: 0,
      running: 0,
      failed_total: 0,
      failed_recent_24h: 0,
      dlq: 0,
    },
  },
  observability: { snapshots_stale_count: 0, monitored_creators: 1 },
  log_path: 'data/monitor-watch.log',
};

describe('mergeRuntimePatch', () => {
  it('merges health diff from WS', () => {
    const next = mergeRuntimePatch(base, { health: 'degraded', health_reasons: ['live tick stale'] });
    expect(next?.health).toBe('degraded');
    expect(next?.daemon.running).toBe(true);
  });

  it('merges queue.updated patch', () => {
    const next = mergeRuntimePatch(base, {
      queues: {
        post_process: { pending: 3, running: 1, max_workers: 2 },
        monitor_tasks: base.queues.monitor_tasks,
      },
    });
    expect(next?.queues.post_process.pending).toBe(3);
  });
});
