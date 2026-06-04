import { describe, expect, it } from 'vitest';
import { parsePiEventLine } from '@m2t/shared';

describe('parsePiEventLine', () => {
  it('parses sidecar.ready', () => {
    const line = JSON.stringify({ type: 'sidecar.ready', payload: { version: '0.1.0' } });
    const ev = parsePiEventLine(line);
    expect(ev?.type).toBe('sidecar.ready');
    if (ev?.type === 'sidecar.ready') {
      expect(ev.payload.version).toBe('0.1.0');
    }
  });

  it('parses turn.end', () => {
    const line = JSON.stringify({ type: 'turn.end', payload: { durationMs: 1200 } });
    const ev = parsePiEventLine(line);
    expect(ev?.type).toBe('turn.end');
  });

  it('parses tool.result', () => {
    const line = JSON.stringify({
      type: 'tool.result',
      payload: { ok: true, data: { creators: [] } },
    });
    const ev = parsePiEventLine(line);
    expect(ev?.type).toBe('tool.result');
  });

  it('returns null for invalid json', () => {
    expect(parsePiEventLine('not json')).toBeNull();
  });
});
