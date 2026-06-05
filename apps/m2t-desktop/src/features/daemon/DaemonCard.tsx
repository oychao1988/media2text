import { useCallback, useEffect, useState } from 'react';
import { apiGet, apiPost } from '../../lib/api';
import { showToast } from '../../lib/toast';
import type { DaemonStatus } from '../../lib/types';

export function DaemonCard() {
  const [status, setStatus] = useState<DaemonStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [logsOpen, setLogsOpen] = useState(true);
  const [logLines, setLogLines] = useState<string[]>([]);

  const refresh = useCallback(async () => {
    try {
      const res = await apiGet<{ ok: boolean } & DaemonStatus>('/api/daemon', true);
      setStatus(res);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const loadLogs = useCallback(async () => {
    try {
      const res = await apiGet<{ ok: boolean; lines: string[] }>('/api/daemon/logs?tail=5', true);
      setLogLines(res.lines ?? []);
    } catch {
      setLogLines([]);
    }
  }, []);

  useEffect(() => {
    if (logsOpen) void loadLogs();
  }, [logsOpen, loadLogs]);

  const startDaemon = async () => {
    if (busy || !status) return;
    setBusy(true);
    try {
      await apiPost('/api/daemon/start');
      showToast('守护进程已启动', 'success');
      await refresh();
    } catch {
      /* toast handled by api */
    } finally {
      setBusy(false);
    }
  };

  const stopDaemon = async () => {
    if (busy || !status) return;
    setBusy(true);
    try {
      await apiPost('/api/daemon/stop');
      showToast('已发送停止守护进程信号', 'success');
      await refresh();
    } catch {
      /* toast handled by api */
    } finally {
      setBusy(false);
    }
  };

  const running = status?.running ?? false;
  const cardClass = `daemon-card${running ? '' : ' stopped'}`;

  useEffect(() => {
    document.getElementById('app')?.classList.toggle('daemon-stopped', !running && !loading);
  }, [running, loading]);

  const meta = status
    ? `PID ${status.pid ?? '—'} · LiveTick ${status.live_tick_interval_sec}s · 后处理 pending ${status.post_process.pending} · running ${status.post_process.running} · 监控任务 pending ${status.monitor_tasks?.pending ?? 0} · running ${status.monitor_tasks?.running ?? 0}${(status.monitor_tasks?.failed ?? 0) > 0 ? ` · failed ${status.monitor_tasks?.failed}` : ''}`
    : loading
      ? '加载中…'
      : '无法获取状态';

  return (
    <div className={cardClass} id="daemon-card">
      <div className="daemon-card-head">
        <div className="daemon-status">
          <span className={`status-dot${running ? ' live' : ''}`} aria-hidden="true" />
          <strong>{running ? 'Daemon 运行中' : 'Daemon 已停止'}</strong>
        </div>
        <div className="daemon-card-actions">
          {running ? (
            <button
              type="button"
              className="icon-btn icon-btn-danger"
              id="btn-daemon-stop"
              title="停止 monitor watch"
              aria-label="停止"
              disabled={busy || loading}
              onClick={() => void stopDaemon()}
            >
              ⏹
            </button>
          ) : (
            <button
              type="button"
              className="icon-btn"
              title="启动 monitor watch"
              aria-label="启动"
              disabled={busy || loading}
              onClick={() => void startDaemon()}
            >
              {busy ? '…' : '▶'}
            </button>
          )}
          <button
            type="button"
            className={`icon-btn daemon-log-toggle${logsOpen ? ' active' : ''}`}
            id="btn-daemon-log"
            title={logsOpen ? '隐藏日志' : '显示日志'}
            aria-label="日志"
            aria-pressed={logsOpen}
            onClick={() => setLogsOpen((v) => !v)}
          >
            ▤
          </button>
        </div>
      </div>
      <div className="daemon-meta">{meta}</div>
      <pre
        className="daemon-log-lines"
        id="daemon-log-panel"
        aria-label="守护进程日志"
        hidden={!logsOpen}
      >
        {logLines.length ? logLines.join('\n') : '（暂无日志）'}
      </pre>
    </div>
  );
}

export function useDaemonActions() {
  const restartDaemon = useCallback(async () => {
    try {
      await apiPost('/api/daemon/stop', undefined, true);
      await apiPost('/api/daemon/start');
      showToast('守护进程已重启', 'success');
    } catch {
      showToast('守护进程重启失败', 'error');
    }
  }, []);

  return { restartDaemon };
}

export function useDaemonRunning(): boolean | null {
  const [running, setRunning] = useState<boolean | null>(null);
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await apiGet<{ running: boolean }>('/api/daemon', true);
        if (!cancelled) setRunning(res.running);
      } catch {
        if (!cancelled) setRunning(null);
      }
    };
    void poll();
    const id = window.setInterval(() => void poll(), 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);
  return running;
}
