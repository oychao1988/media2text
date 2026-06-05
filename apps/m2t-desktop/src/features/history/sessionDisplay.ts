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
  if (!end) return fmt(start);
  return `${fmt(start)} – ${fmt(end)}`;
}

export function historyKindLabel(session: LiveSessionSummary): string {
  if (session.kind === 'vod') {
    return sessionIsGallery(session) ? '图文' : '作品';
  }
  return '直播';
}

export function historyRowTitle(session: LiveSessionSummary): string {
  if (session.kind === 'vod') {
    return session.title?.trim() || '未命名作品';
  }
  return formatSessionTime(session.started_at, session.ended_at);
}

export function sessionPlaybackLabel(session: LiveSessionSummary): string {
  if (session.kind === 'vod') {
    return session.title?.trim() || '作品';
  }
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

export function sessionCloudAvailable(session: LiveSessionSummary): boolean {
  if (session.cloud_available) return true;
  const status = session.cloud_upload_status;
  if (status === 'done' || status === 'uploaded') {
    return Boolean(session.cloud_file_id || session.cloud_relative_path);
  }
  return false;
}

export function sessionCloudLabel(session: LiveSessionSummary): { text: string; className: string } {
  const status = session.cloud_upload_status;
  if (status === 'failed') return { text: '云端失败', className: 'fail' };
  if (status === 'skipped') return { text: '云端跳过', className: 'miss' };
  if (status === 'pending') return { text: '云端待传', className: 'miss' };

  if (sessionCloudAvailable(session)) {
    if (!session.media_available) return { text: '☁ 仅云端', className: 'cloud' };
    return { text: '☁ 已备份', className: 'cloud' };
  }
  return { text: '云端 —', className: 'miss' };
}

export function sessionIsGallery(session: LiveSessionSummary): boolean {
  return session.kind === 'vod' && session.media_type === 'gallery';
}

export function sessionIsListedPending(session: LiveSessionSummary): boolean {
  return session.kind === 'vod' && session.status === 'listed';
}

export function sessionLocalLabel(session: LiveSessionSummary): { text: string; className: string } {
  if (sessionIsListedPending(session)) return { text: '本地 —', className: 'miss' };
  if (session.media_available) return { text: '本地 ✓', className: 'ok' };
  if (sessionMediaPath(session)) return { text: '本地缺失', className: 'miss' };
  return { text: '本地 —', className: 'miss' };
}

/** 历史列表：仅在失败时展示状态标签（成功/录制中等不展示）。 */
export function sessionStatusTag(
  session: LiveSessionSummary,
): { text: string; className: string } | null {
  if (sessionIsListedPending(session)) return { text: '待下载', className: 'miss' };
  if (session.status !== 'failed') return null;
  return { text: '失败', className: 'fail' };
}

export function sessionCloudOnly(session: LiveSessionSummary): boolean {
  return sessionCloudAvailable(session) && !session.media_available;
}

export function sessionIsDisabled(session: LiveSessionSummary): boolean {
  if (session.kind === 'vod') {
    return session.status === 'failed' && !sessionMediaPath(session);
  }
  if (session.status === 'failed' && !sessionMediaPath(session)) return true;
  return false;
}

export function sessionCanDownloadCloud(session: LiveSessionSummary): boolean {
  return session.kind === 'live' && sessionCloudAvailable(session) && !session.media_available;
}

export function sessionCanRetryVodDownload(session: LiveSessionSummary): boolean {
  return session.kind === 'vod' && session.status === 'failed';
}

export function sessionCanDeleteLocal(session: LiveSessionSummary): boolean {
  return Boolean(session.media_available && sessionMediaPath(session));
}
