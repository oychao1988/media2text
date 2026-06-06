import { agentAbbr, resolveAgentProfile, AGENT_GLOBAL_PROFILE } from './agentProfile';
import { formatChatTime } from './formatChatTime';
import { describe, expect, it } from 'vitest';

describe('agentProfile', () => {
  it('resolves global profile when thread has no creator', () => {
    expect(resolveAgentProfile(null, [])).toEqual(AGENT_GLOBAL_PROFILE);
  });

  it('resolves creator display name', () => {
    const profile = resolveAgentProfile('c1', [
      { id: 'c1', display_name: '老番茄' },
    ]);
    expect(profile.name).toBe('老番茄');
    expect(profile.abbr).toBe('老番');
  });

  it('abbreviates short names', () => {
    expect(agentAbbr('灵犀')).toBe('灵犀');
  });
});

describe('formatChatTime', () => {
  it('formats ISO timestamps in local time', () => {
    const iso = '2026-06-07T14:31:11.000Z';
    const formatted = formatChatTime(iso);
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, '0');
    const expected = `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    expect(formatted).toBe(expected);
  });

  it('returns null for invalid input', () => {
    expect(formatChatTime(undefined)).toBeNull();
    expect(formatChatTime('not-a-date')).toBeNull();
  });
});
