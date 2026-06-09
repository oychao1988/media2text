/** Map media element time to transcript timeline (S4 / discontinuity_at). */
export function alignPlaybackTime(
  mediaTime: number,
  discontinuityAt: number[] | undefined,
  partDurations?: number[],
): number {
  if (mediaTime <= 0) {
    return 0;
  }

  if (partDurations?.length) {
    let mediaCursor = 0;
    let transcriptTime = 0;
    for (const raw of partDurations) {
      const dur = Number(raw);
      if (!Number.isFinite(dur) || dur <= 0) {
        continue;
      }
      const partEnd = mediaCursor + dur;
      if (mediaTime <= partEnd) {
        return transcriptTime + (mediaTime - mediaCursor);
      }
      transcriptTime += dur;
      mediaCursor = partEnd;
    }
    return transcriptTime + Math.max(0, mediaTime - mediaCursor);
  }

  if (!discontinuityAt?.length) {
    return mediaTime;
  }

  const bounds = [...discontinuityAt].sort((a, b) => a - b);
  let transcriptTime = 0;
  let prevBound = 0;
  for (const bound of bounds) {
    if (mediaTime < bound) {
      return transcriptTime + (mediaTime - prevBound);
    }
    transcriptTime = bound;
    prevBound = bound;
  }
  return transcriptTime + (mediaTime - prevBound);
}

export function sessionUsesHls(session: {
  media_format?: string | null;
  media_path?: string | null;
  local_path?: string | null;
  temp_path?: string | null;
}): boolean {
  if (session.media_format === 'hls') return true;
  const paths = [session.media_path, session.local_path, session.temp_path];
  return paths.some((p) => typeof p === 'string' && p.toLowerCase().endsWith('.m3u8'));
}
