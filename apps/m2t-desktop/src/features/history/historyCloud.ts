import type { LiveSessionSummary } from '../../lib/types';

export type SessionEnrichFields = Pick<
  LiveSessionSummary,
  | 'cloud_upload_status'
  | 'cloud_file_id'
  | 'cloud_relative_path'
  | 'cloud_available'
  | 'has_transcript'
  | 'has_summary'
  | 'media_available'
  | 'media_path'
  | 'media_format'
  | 'discontinuity_at'
  | 'part_durations'
  | 'transcript_path'
  | 'summary_path'
>;

/** @deprecated use SessionEnrichFields */
export type SessionCloudFields = Pick<
  LiveSessionSummary,
  'cloud_upload_status' | 'cloud_file_id' | 'cloud_relative_path' | 'cloud_available'
>;

export function sessionCloudKey(session: Pick<LiveSessionSummary, 'kind' | 'item_id'>): string {
  return `${session.kind}:${session.item_id}`;
}

export function mergeSessionEnrichInfo(
  sessions: LiveSessionSummary[],
  items: Record<string, SessionEnrichFields>,
): LiveSessionSummary[] {
  if (!Object.keys(items).length) return sessions;
  return sessions.map((session) => {
    const enrich = items[sessionCloudKey(session)];
    if (!enrich) return session;
    return { ...session, ...enrich };
  });
}

/** @deprecated use mergeSessionEnrichInfo */
export function mergeSessionCloudInfo(
  sessions: LiveSessionSummary[],
  items: Record<string, SessionCloudFields>,
): LiveSessionSummary[] {
  return mergeSessionEnrichInfo(sessions, items);
}
