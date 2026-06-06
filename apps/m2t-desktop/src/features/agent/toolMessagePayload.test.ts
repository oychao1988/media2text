import { describe, expect, it } from 'vitest';
import { parseToolMessagePayload } from './toolMessagePayload';

describe('parseToolMessagePayload', () => {
  it('wraps data-only JSON as successful tool result', () => {
    const content = JSON.stringify({ skills: [{ name: 'media2text' }] });
    const { payload, toolName } = parseToolMessagePayload(content, 'skills_list');
    expect(payload.ok).toBe(true);
    expect(payload.data).toEqual({ skills: [{ name: 'media2text' }] });
    expect(toolName).toBe('skills_list');
  });

  it('preserves full payload when ok is present', () => {
    const content = JSON.stringify({
      ok: false,
      error: { code: 'UNKNOWN_TOOL', message: 'unknown tool: foo' },
    });
    const { payload } = parseToolMessagePayload(content);
    expect(payload.ok).toBe(false);
    expect(payload.error?.code).toBe('UNKNOWN_TOOL');
  });

  it('treats plain text as tool failure message', () => {
    const { payload } = parseToolMessagePayload('skill not found: missing');
    expect(payload.ok).toBe(false);
    expect(payload.error?.message).toBe('skill not found: missing');
  });
});
