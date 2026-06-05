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
  if (!session.started_at) return session.session_id;
  try {
    const d = new Date(session.started_at);
    const day = d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).replace(/\//g, '-');
    const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
    return `${day} ${time}`;
  } catch {
    return session.session_id;
  }
}

export function sessionMediaPath(session: LiveSessionSummary): string | null {
  return session.media_path ?? session.local_path ?? session.temp_path ?? null;
}

export function sessionMediaMissing(session: LiveSessionSummary): boolean {
  return Boolean(sessionMediaPath(session)) && !session.media_available;
}

export function sessionIsDisabled(session: LiveSessionSummary): boolean {
  if (session.status === 'failed' && !sessionMediaPath(session)) return true;
  return false;
}
