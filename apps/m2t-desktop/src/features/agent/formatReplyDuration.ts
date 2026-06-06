/** Whole-turn duration for agent replies (seconds, min 1). */
export function replyDurationSeconds(durationMs: number | undefined): number | null {
  if (durationMs == null || durationMs < 0) return null;
  return Math.max(1, Math.round(durationMs / 1000));
}

export function formatReplyDurationLabel(durationMs: number | undefined): string | null {
  const seconds = replyDurationSeconds(durationMs);
  return seconds != null ? `耗时 ${seconds} 秒` : null;
}
