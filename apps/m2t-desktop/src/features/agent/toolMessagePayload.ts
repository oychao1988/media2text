import type { ToolResultPayload } from '@m2t/shared';

/** Reconstruct UI payload from DB tool message content (LLM-facing text/JSON). */
export function parseToolMessagePayload(
  content: string,
  toolName?: string | null,
): { payload: ToolResultPayload; toolName?: string } {
  const trimmed = (content || '').trim();
  const resolvedName = toolName?.trim() || undefined;

  if (!trimmed) {
    return {
      payload: {
        ok: false,
        error: { code: 'EMPTY', message: 'empty tool result' },
      },
      toolName: resolvedName,
    };
  }

  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const obj = parsed as Record<string, unknown>;
      if (typeof obj.ok === 'boolean') {
        const nameFromPayload = typeof obj.name === 'string' ? obj.name : undefined;
        const { name: _ignored, ...rest } = obj;
        return {
          payload: rest as ToolResultPayload,
          toolName: resolvedName ?? nameFromPayload,
        };
      }
      return {
        payload: { ok: true, data: parsed },
        toolName: resolvedName,
      };
    }
  } catch {
    /* plain-text tool output */
  }

  return {
    payload: {
      ok: false,
      error: { code: 'TOOL_FAILED', message: trimmed },
    },
    toolName: resolvedName,
  };
}
