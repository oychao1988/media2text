import { logLineClass, parseDaemonLogLine, statusClass, type ParsedDaemonLogLine } from './daemonLog';

type Props = {
  entry: ParsedDaemonLogLine;
};

export function DaemonLogLineView({ entry }: Props) {
  return (
    <div className={logLineClass(entry)}>
      <div className="daemon-log-main">
        {entry.time ? <span className="daemon-log-time">[{entry.time}]</span> : null}
        <span className={statusClass(entry.status)}>{entry.status}</span>
        <span className="daemon-log-task">{entry.task}</span>
        <span className="daemon-log-target">{entry.target}</span>
      </div>
      {entry.detail ? <div className="daemon-log-detail">{entry.detail}</div> : null}
    </div>
  );
}

export function daemonLogLineFromText(line: string): ParsedDaemonLogLine {
  return (
    parseDaemonLogLine(line) ?? {
      time: '',
      status: '信息',
      task: '系统',
      target: '—',
      detail: line,
      level: 'info',
      raw: line,
    }
  );
}
