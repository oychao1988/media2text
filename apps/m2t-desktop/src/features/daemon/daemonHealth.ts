import type {
  RuntimeHealth,
  RuntimeStatus,
} from '../../lib/types';

export const HEALTH_TITLE: Record<RuntimeHealth, string> = {
  healthy: '运行正常',
  degraded: '需要关注',
  stopped: '已停止',
};

export const HEALTH_HINT: Record<RuntimeHealth, string> = {
  healthy: '正在自动检测直播并同步作品',
  degraded: '后台仍在运行，部分检测可能偏慢',
  stopped: '未检测直播，也不会同步新作品',
};

export type DaemonStat = { label: string; value: string };

export type HealthAlert = {
  text: string;
  action?: 'recover-stale' | 'show-stale-creators';
};

export type WorkQueueMonitorTask = {
  id: string;
  task_type: string;
  task_label: string;
  creator_id: string;
  creator_name: string;
  status: string;
  started_at: string | null;
  running_sec: number | null;
  error: string | null;
};

export type WorkQueuePostProcess = {
  id: string;
  session_id: string;
  creator_id: string;
  creator_name: string;
  status: string;
  stage: string | null;
  media_name: string | null;
  running_sec: number | null;
  error: string | null;
};

export type WorkQueueStaleCreator = {
  creator_id: string;
  display_name: string;
  checked_at: string | null;
  stale_sec: number | null;
};

export type WorkQueue = {
  ok: boolean;
  monitor_tasks: WorkQueueMonitorTask[];
  post_process: WorkQueuePostProcess[];
  stale_creators: WorkQueueStaleCreator[];
};

export function formatHealthReason(reason: string): string {
  if (reason === 'live tick stale') {
    return '直播检测心跳超时，轮询可能已卡住';
  }
  if (reason === 'monitor not running') {
    return '后台监控未启动';
  }
  const staleMatch = /^(\d+) creator snapshots stale$/.exec(reason);
  if (staleMatch) {
    return `${staleMatch[1]} 位博主的开播状态长时间未刷新（监控停止或检测异常时常见）`;
  }
  const failMatch = /^(\d+) monitor task failures in 24h$/.exec(reason);
  if (failMatch) {
    return `近 24 小时有 ${failMatch[1]} 次作品同步或下载失败，可在下方任务列表重试`;
  }
  return reason;
}

export function buildHealthAlerts(reasons: string[]): HealthAlert[] {
  return reasons.map((reason) => {
    const text = formatHealthReason(reason);
    if (/开播状态长时间未刷新|snapshots stale/i.test(reason)) {
      return { text, action: 'show-stale-creators' };
    }
    if (/failures in 24h/i.test(reason) || reason === 'live tick stale') {
      return { text, action: 'recover-stale' };
    }
    return { text };
  });
}

export const DAEMON_CARD_TITLE = '后台监控';

export function healthAriaLabel(health: RuntimeHealth, running: boolean): string {
  if (!running || health === 'stopped') {
    return `${DAEMON_CARD_TITLE}：已停止`;
  }
  if (health === 'degraded') {
    return `${DAEMON_CARD_TITLE}：异常，部分检测可能偏慢`;
  }
  return `${DAEMON_CARD_TITLE}：运行正常`;
}

export function formatTickAge(
  tickAgeSec: number | null | undefined,
  intervalSec: number,
): string {
  if (tickAgeSec == null) return '暂无心跳';
  const sec = Math.max(0, Math.round(tickAgeSec));
  if (sec <= intervalSec) return `${sec} 秒前`;
  return `${sec} 秒前（偏慢）`;
}

export function formatRunningSec(sec: number | null | undefined): string {
  if (sec == null) return '';
  const s = Math.max(0, Math.round(sec));
  if (s < 60) return `${s} 秒`;
  if (s < 3600) return `${Math.round(s / 60)} 分钟`;
  return `${Math.round(s / 3600)} 小时`;
}

export function buildDaemonStats(runtime: RuntimeStatus): DaemonStat[] {
  const { queues } = runtime;
  const pp = queues.post_process;
  const mt = queues.monitor_tasks;
  const pid = runtime.daemon.pid;
  const pidSuffix = pid != null ? ` · PID ${pid}` : '';
  const stats: DaemonStat[] = [
    {
      label: '运行方式',
      value:
        runtime.managed_by === 'embedded'
          ? `Desktop 内嵌${pidSuffix}`
          : runtime.managed_by === 'external'
            ? `终端守护进程${pidSuffix}`
            : '未运行',
    },
    {
      label: '录后处理',
      value: `${pp.pending} 排队 · ${pp.running} 进行中`,
    },
  ];
  if (mt.pending > 0 || mt.running > 0) {
    stats.push({
      label: '作品任务',
      value: `${mt.pending} 排队 · ${mt.running} 进行中`,
    });
  }
  return stats;
}

export function workQueueHasItems(queue: WorkQueue | null): boolean {
  if (!queue) return false;
  return (
    queue.monitor_tasks.length > 0 ||
    queue.post_process.length > 0 ||
    queue.stale_creators.length > 0
  );
}

/** @deprecated use buildDaemonStats */
export function buildMeta(runtime: RuntimeStatus): string {
  return buildDaemonStats(runtime)
    .map((s) => `${s.label} ${s.value}`)
    .join(' · ');
}
