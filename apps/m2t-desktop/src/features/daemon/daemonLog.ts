export type DaemonLogEntry = {
  time: string | null;
  status: string;
  task: string;
  target: string;
  detail: string | null;
  level: string;
  line: string;
};

export type ParsedDaemonLogLine = {
  time: string;
  status: string;
  task: string;
  target: string;
  detail: string | null;
  level: string;
  raw: string;
};

const STRUCTURED_RE = /^\[(\d{2}:\d{2}:\d{2})\]\s+(.+)$/;

export function parseDaemonLogLine(line: string): ParsedDaemonLogLine | null {
  const raw = line.trim();
  if (!raw) return null;
  const match = raw.match(STRUCTURED_RE);
  if (!match) {
    return {
      time: '',
      status: '信息',
      task: '系统',
      target: '—',
      detail: raw,
      level: 'info',
      raw,
    };
  }
  const parts = match[2].split(' · ').map((p) => p.trim());
  return {
    time: match[1],
    status: parts[0] ?? '信息',
    task: parts[1] ?? '—',
    target: parts[2] ?? '—',
    detail: parts.length > 3 ? parts.slice(3).join(' · ') : null,
    level: inferLevel(parts[0] ?? ''),
    raw,
  };
}

export function entryFromApi(entry: DaemonLogEntry): ParsedDaemonLogLine {
  return {
    time: entry.time ?? '',
    status: entry.status,
    task: entry.task,
    target: entry.target,
    detail: entry.detail,
    level: entry.level,
    raw: entry.line,
  };
}

function inferLevel(status: string): string {
  if (/失败/.test(status)) return 'error';
  if (/警告|跳过/.test(status)) return 'warning';
  if (/完成|启动|停止|空闲/.test(status)) return 'info';
  return 'info';
}

export function logLineClass(entry: ParsedDaemonLogLine): string {
  if (entry.level === 'error' || /失败/.test(entry.status)) {
    return 'daemon-log-line warn';
  }
  if (entry.level === 'warning' || /警告/.test(entry.status)) {
    return 'daemon-log-line warn';
  }
  if (/完成|启动|空闲/.test(entry.status)) {
    return 'daemon-log-line ok';
  }
  return 'daemon-log-line';
}

export function statusClass(status: string): string {
  if (/失败/.test(status)) return 'daemon-log-status is-error';
  if (/警告|跳过/.test(status)) return 'daemon-log-status is-warn';
  if (/完成|启动/.test(status)) return 'daemon-log-status is-ok';
  if (/进行中|排队|空闲/.test(status)) return 'daemon-log-status is-active';
  if (/停止/.test(status)) return 'daemon-log-status is-stopped';
  return 'daemon-log-status';
}
