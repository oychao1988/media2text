/** Map media element time to transcript timeline (S4 / discontinuity_at). */
export function alignPlaybackTime(
  mediaTime: number,
  discontinuityAt: number[] | undefined,
): number {
  if (!discontinuityAt?.length || mediaTime <= 0) {
    return mediaTime;
  }
  // HLS event playlists expose a continuous media timeline; discontinuity_at
  // records reconnect boundaries for transcript alignment (S4). Offline-gap
  // compensation needs per-part durations from session.manifest.json (future).
  void discontinuityAt;
  return mediaTime;
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
