import type { ToolResultPayload, TurnPhaseKind } from '@m2t/shared';

let stdoutErrorHooked = false;

/** Tauri / start-sidecar may close the read end during React Strict Mode remount. */
function ensureStdoutErrorHook(): void {
  if (stdoutErrorHooked) return;
  stdoutErrorHooked = true;
  process.stdout.on('error', (err: NodeJS.ErrnoException) => {
    if (err.code === 'EPIPE') return;
    throw err;
  });
}

export function emit(event: { type: string; payload: unknown }): void {
  ensureStdoutErrorHook();
  process.stdout.write(`${JSON.stringify(event)}\n`);
}

export function emitReady(version: string): void {
  emit({ type: 'sidecar.ready', payload: { version } });
}

export function emitError(message: string, code?: string): void {
  emit({ type: 'error', payload: { message, code } });
}

export function emitTurnStart(startedAt?: number): void {
  emit({ type: 'turn.start', payload: { startedAt } });
}

export function emitTurnPhase(phase: TurnPhaseKind, label: string): void {
  emit({ type: 'turn.phase', payload: { phase, label } });
}

export function emitThinking(text: string): void {
  emit({ type: 'message.thinking', payload: { text } });
}

export function emitAssistantDelta(delta: string): void {
  emit({ type: 'message.assistant.delta', payload: { delta } });
}

export function emitAssistant(
  text: string,
  meta?: { durationMs?: number; thinkingText?: string },
): void {
  emit({
    type: 'message.assistant',
    payload: {
      text,
      durationMs: meta?.durationMs,
      thinkingText: meta?.thinkingText?.trim() || undefined,
    },
  });
}

export function emitTurnEnd(durationMs: number): void {
  emit({ type: 'turn.end', payload: { durationMs } });
}

export function emitToolResult(payload: ToolResultPayload): void {
  emit({ type: 'tool.result', payload });
}
