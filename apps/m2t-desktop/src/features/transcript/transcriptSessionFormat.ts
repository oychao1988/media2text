import type { SessionListItem } from './transcriptSelection';

export function formatSessionOptionMeta(startedAt: string | null | undefined): string | undefined {
  if (!startedAt) return undefined;
  try {
    const d = new Date(startedAt);
    if (Number.isNaN(d.getTime())) return undefined;
    const now = new Date();
    const sameYear = d.getFullYear() === now.getFullYear();
    const date = sameYear
      ? d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }).replace(/\//g, '-')
      : d.toLocaleDateString('zh-CN', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
        }).replace(/\//g, '-');
    const time = d.toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
    return `${date} ${time}`;
  } catch {
    return undefined;
  }
}

export function sessionOptionTitle(row: SessionListItem): string {
  if (row.kind === 'vod') {
    const title = row.title?.trim() || row.display_label?.trim();
    return title || '未命名作品';
  }
  const label = row.display_label?.trim() || '直播';
  return label.replace(/^\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}\s*/, '').trim() || '直播';
}
