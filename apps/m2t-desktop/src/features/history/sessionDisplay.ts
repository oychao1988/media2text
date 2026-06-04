import type { LiveSessionSummary } from '../../lib/types';

export function formatSessionDuration(
  started: string | null,
  ended: string | null,
): string | null {
  if (!started || !ended) return null;
  try {
    const ms = new Date(ended).getTime() - new Date(started).getTime();
    if (ms <= 0 || Number.isNaN(ms)) return null;
    const mins = Math.round(ms / 60000);
    if (mins < 60) return `${mins}m`;
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m ? `${h}h ${m}m` : `${h}h`;
  } catch {
    return null;
  }
}

export function formatSessionTime(start: string | null, end: string | null): string {
  const fmt = (iso: string | null) => {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
    } catch {
      return iso;
    }
  };
  return `${fmt(start)} – ${fmt(end)}`;
}

export function sessionSizeLabel(session: LiveSessionSummary): string {
  if (session.status === 'failed' && !session.media_path) return '—';
  if (session.cloud_upload_status === 'uploaded' && !session.local_path) return '云端';
  const path = session.media_path ?? session.local_path ?? session.temp_path;
  if (!path) return '—';
  const base = path.split('/').pop();
  return base ?? '—';
}

export function sessionPlaybackLabel(session: LiveSessionSummary): string {
  const day = session.started_at?.slice(0, 10) ?? '';
  const time = session.started_at?.slice(11, 16) ?? '';
  return day && time ? `${day} ${time}` : session.session_id;
}

export function sessionIsDisabled(session: LiveSessionSummary): boolean {
  return session.status === 'failed' && !session.media_path && !session.local_path;
}
