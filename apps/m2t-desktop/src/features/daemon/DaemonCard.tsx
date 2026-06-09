import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiGet, apiPost, ApiError } from '../../lib/api';
import type { RuntimeHealth, RuntimeStatus } from '../../lib/types';
import { useRuntime } from '../runtime/RuntimeContext';
import {
  DAEMON_CARD_TITLE,
  buildDaemonStats,
  formatRunningSec,
  healthAriaLabel,
  workQueueHasItems,
  type WorkQueue,
} from './daemonHealth';
import { DaemonLogLineView, daemonLogLineFromText } from './DaemonLogLine';
import { entryFromApi, type DaemonLogEntry, type ParsedDaemonLogLine } from './daemonLog';

const LOG_REFRESH_MS = 12_000;
const LOG_TAIL = 8;
const WORK_QUEUE_REFRESH_MS = 15_000;

type BottomPanel = 'logs' | 'tasks' | null;

type Props = {
  onSelectCreator?: (creatorId: string) => void;
};

export function DaemonCard({ onSelectCreator }: Props) {
  const { runtime, loading, fetchError, startRuntime, stopRuntime, takeoverRuntime, refresh } = useRuntime();
  const [busy, setBusy] = useState(false);
  const [recoverBusy, setRecoverBusy] = useState(false);
  const [bottomPanel, setBottomPanel] = useState<BottomPanel>('logs');
  const [logEntries, setLogEntries] = useState<ParsedDaemonLogLine[]>([]);
  const [workQueue, setWorkQueue] = useState<WorkQueue | null>(null);

  const health: RuntimeHealth = runtime?.health ?? 'stopped';
  const running = runtime?.daemon.running ?? false;
  const external = runtime?.managed_by === 'external';
  const canControl = !external;
  const stats = runtime ? buildDaemonStats(runtime) : [];
  const showBottomPanel = Boolean(runtime) && !fetchError;

  const toggleBottomPanel = (panel: Exclude<BottomPanel, null>) => {
    setBottomPanel((current) => (current === panel ? null : panel));
  };

  const loadLogs = useCallback(async () => {
    try {
      const res = await apiGet<{ ok: boolean; lines: string[]; entries?: DaemonLogEntry[] }>(
        `/api/runtime/logs?tail=${LOG_TAIL}`,
        true,
      );
      const entries = (res.entries ?? []).map(entryFromApi);
      if (entries.length > 0) {
        setLogEntries(entries);
        return;
      }
      setLogEntries((res.lines ?? []).map(daemonLogLineFromText));
    } catch {
      setLogEntries([]);
    }
  }, []);

  const loadWorkQueue = useCallback(async () => {
    try {
      const res = await apiGet<WorkQueue>('/api/runtime/work-queue?limit=12', true);
      setWorkQueue(res);
    } catch {
      setWorkQueue(null);
    }
  }, []);

  useEffect(() => {
    if (bottomPanel !== 'logs') return undefined;
    void loadLogs();
    const id = window.setInterval(() => void loadLogs(), LOG_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [bottomPanel, loadLogs]);

  useEffect(() => {
    if (bottomPanel !== 'tasks' || !runtime || fetchError) return undefined;
    void loadWorkQueue();
    const id = window.setInterval(() => void loadWorkQueue(), WORK_QUEUE_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [bottomPanel, runtime, fetchError, loadWorkQueue]);

  const cardClass = useMemo(() => {
    const extra = health === 'stopped' ? ' stopped' : health === 'degraded' ? ' degraded' : '';
    return `daemon-card${extra}`;
  }, [health]);

  const onTakeover = async () => {
    if (busy || !runtime) return;
    setBusy(true);
    try {
      await takeoverRuntime();
    } finally {
      setBusy(false);
    }
  };

  const onStart = async () => {
    if (busy || !runtime || !canControl) return;
    setBusy(true);
    try {
      await startRuntime();
    } finally {
      setBusy(false);
    }
  };

  const onStop = async () => {
    if (busy || !runtime || !canControl) return;
    setBusy(true);
    try {
      await stopRuntime();
    } finally {
      setBusy(false);
    }
  };

  const onRecoverStale = async () => {
    if (recoverBusy) return;
    setRecoverBusy(true);
    try {
      await apiPost('/api/runtime/recover-stale?older_than_sec=120', undefined, true);
      await Promise.all([refresh(), loadWorkQueue()]);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : '清理失败';
      window.alert(msg);
    } finally {
      setRecoverBusy(false);
    }
  };

  const pickCreator = (creatorId: string) => {
    onSelectCreator?.(creatorId);
  };

  return (
    <div className={cardClass} id="daemon-card">
      <div className="daemon-card-head">
        <div className="daemon-status">
          <span
            className={`status-dot health-${health}${running ? ' live' : ''}`}
            role="img"
            aria-label={healthAriaLabel(health, running)}
          />
          <div className="daemon-status-text">
            <strong>{DAEMON_CARD_TITLE}</strong>
            {fetchError ? <span className="daemon-hint">{fetchError}</span> : null}
          </div>
        </div>
        <div className="daemon-card-actions">
          {external ? (
            <button
              type="button"
              className="btn btn-sm"
              id="btn-daemon-takeover"
              title="停止终端里单独启动的 monitor watch，改由 Desktop 启停"
              disabled={busy}
              onClick={() => void onTakeover()}
            >
              改用 Desktop 管理
            </button>
          ) : running ? (
            <button
              type="button"
              className="icon-btn icon-btn-danger"
              id="btn-daemon-stop"
              title="停止后台监控"
              aria-label="停止"
              disabled={busy || loading}
              onClick={() => void onStop()}
            >
              ⏹
            </button>
          ) : (
            <button
              type="button"
              className="icon-btn"
              title="启动后台监控"
              aria-label="启动"
              disabled={busy || loading}
              onClick={() => void onStart()}
            >
              {busy ? '…' : '▶'}
            </button>
          )}
          <button
            type="button"
            className={`icon-btn daemon-panel-toggle${bottomPanel === 'tasks' ? ' active' : ''}`}
            id="btn-daemon-tasks"
            title={bottomPanel === 'tasks' ? '隐藏任务详情' : '显示任务详情'}
            aria-label="任务详情"
            aria-pressed={bottomPanel === 'tasks'}
            disabled={!showBottomPanel}
            onClick={() => toggleBottomPanel('tasks')}
          >
            ☰
          </button>
          <button
            type="button"
            className={`icon-btn daemon-panel-toggle${bottomPanel === 'logs' ? ' active' : ''}`}
            id="btn-daemon-log"
            title={bottomPanel === 'logs' ? '隐藏最近日志' : '显示最近日志'}
            aria-label="日志"
            aria-pressed={bottomPanel === 'logs'}
            disabled={!showBottomPanel}
            onClick={() => toggleBottomPanel('logs')}
          >
            ▤
          </button>
        </div>
      </div>

      {runtime && !fetchError ? (
        <dl className="daemon-stats">
          {stats.map((row) => (
            <div className="daemon-stat" key={row.label}>
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {bottomPanel === 'logs' ? (
        <div className="daemon-log-panel" id="daemon-log-panel" aria-label="最近运行日志">
          {logEntries.length ? (
            logEntries.map((entry, index) => (
              <DaemonLogLineView key={`${entry.raw}-${index}`} entry={entry} />
            ))
          ) : (
            <div className="daemon-log-empty">暂无日志</div>
          )}
        </div>
      ) : null}

      {bottomPanel === 'tasks' ? (
        <div className="daemon-log-panel daemon-tasks-panel" id="daemon-tasks-panel" aria-label="任务详情">
          <div className="daemon-work-queue-body">
            {(workQueue?.post_process.length ?? 0) > 0 ? (
              <section className="daemon-work-section">
                <h4>录后处理</h4>
                <ul>
                  {workQueue!.post_process.map((job) => (
                    <li key={job.id}>
                      <button
                        type="button"
                        className="daemon-work-item"
                        onClick={() => pickCreator(job.creator_id)}
                      >
                        <span className="daemon-work-primary">
                          {job.creator_name}
                          {job.media_name ? ` · ${job.media_name}` : ''}
                        </span>
                        <span className="daemon-work-meta">
                          {job.status === 'running' ? '进行中' : '排队'}
                          {job.stage ? ` · ${job.stage}` : ''}
                          {job.running_sec != null ? ` · ${formatRunningSec(job.running_sec)}` : ''}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
            {(workQueue?.monitor_tasks.length ?? 0) > 0 ? (
              <section className="daemon-work-section">
                <h4>作品 / 同步任务</h4>
                <ul>
                  {workQueue!.monitor_tasks.map((task) => (
                    <li key={task.id}>
                      <button
                        type="button"
                        className="daemon-work-item"
                        onClick={() => pickCreator(task.creator_id)}
                      >
                        <span className="daemon-work-primary">
                          {task.creator_name} · {task.task_label}
                        </span>
                        <span className="daemon-work-meta">
                          {task.status === 'running' ? '进行中' : '排队'}
                          {task.running_sec != null ? ` · ${formatRunningSec(task.running_sec)}` : ''}
                          {task.error ? ` · ${task.error.slice(0, 40)}` : ''}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
            {(workQueue?.stale_creators.length ?? 0) > 0 ? (
              <section className="daemon-work-section">
                <h4>开播状态过期</h4>
                <ul>
                  {workQueue!.stale_creators.map((c) => (
                    <li key={c.creator_id}>
                      <button
                        type="button"
                        className="daemon-work-item"
                        onClick={() => pickCreator(c.creator_id)}
                      >
                        <span className="daemon-work-primary">{c.display_name}</span>
                        <span className="daemon-work-meta">
                          {c.checked_at
                            ? `上次检测 ${formatRunningSec(c.stale_sec)} 前`
                            : '尚未检测'}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
            {!workQueueHasItems(workQueue) ? (
              <p className="daemon-work-empty">暂无排队任务（统计数字可能来自已卡住的旧记录）</p>
            ) : null}
            {(runtime?.queues.monitor_tasks.running ?? 0) > 0 ||
            (runtime?.queues.post_process.running ?? 0) > 0 ? (
              <button
                type="button"
                className="daemon-recover-btn"
                disabled={recoverBusy}
                onClick={() => void onRecoverStale()}
              >
                {recoverBusy ? '清理中…' : '重置卡住的任务计数'}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function useDaemonActions() {
  const { restartRuntime } = useRuntime();
  return { restartDaemon: restartRuntime };
}

export {
  DAEMON_CARD_TITLE,
  HEALTH_TITLE,
  formatHealthReason,
  buildDaemonStats,
  buildDaemonStats as buildMeta,
} from './daemonHealth';
