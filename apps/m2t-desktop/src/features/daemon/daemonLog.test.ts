import { describe, expect, it } from 'vitest';
import { parseDaemonLogLine, statusClass } from './daemonLog';

describe('parseDaemonLogLine', () => {
  it('parses structured backend line', () => {
    const parsed = parseDaemonLogLine(
      '[20:24:31] 进行中 · 直播检测 · 2 场录制中 · 每 20 秒一轮',
    );
    expect(parsed).toMatchObject({
      time: '20:24:31',
      status: '进行中',
      task: '直播检测',
      target: '2 场录制中',
      detail: '每 20 秒一轮',
    });
  });

  it('falls back for plain text', () => {
    const parsed = parseDaemonLogLine('plain log line');
    expect(parsed?.detail).toBe('plain log line');
    expect(parsed?.task).toBe('系统');
  });
});

describe('statusClass', () => {
  it('maps status to css class', () => {
    expect(statusClass('失败')).toContain('is-error');
    expect(statusClass('完成')).toContain('is-ok');
    expect(statusClass('进行中')).toContain('is-active');
  });
});
