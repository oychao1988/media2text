import type { LiveSessionSummary } from '../../lib/types';
import { formatSessionOptionMeta } from '../transcript/transcriptSessionFormat';
import { attachmentId } from './agentAttachments';
import type { ContextAttachment } from './contextAttachment';

export type MentionDocumentRow = {
  rowKey: string;
  creatorId: string;
  creatorName: string;
  sessionKind: 'live' | 'vod';
  itemId: string;
  docType: 'transcript' | 'summary';
  path: string;
  label: string;
  searchText: string;
};

function sessionBaseLabel(session: LiveSessionSummary): string {
  if (session.kind === 'vod') {
    return session.title?.trim() || '未命名作品';
  }
  const meta = formatSessionOptionMeta(session.started_at);
  return meta ? `${meta} 直播` : '直播';
}

export function expandSessionToMentionRows(
  session: LiveSessionSummary,
  creatorName: string,
): MentionDocumentRow[] {
  const base = sessionBaseLabel(session);
  const itemId = session.kind === 'live' ? session.session_id : session.item_id;
  const rows: MentionDocumentRow[] = [];

  if (session.has_transcript && session.transcript_path) {
    const docType = 'transcript' as const;
    const path = session.transcript_path;
    const label = `${creatorName} · ${base} · 转写`;
    rows.push({
      rowKey: `${session.creator_id}:${itemId}:${docType}`,
      creatorId: session.creator_id,
      creatorName,
      sessionKind: session.kind,
      itemId,
      docType,
      path,
      label,
      searchText: `${creatorName} ${base} 转写 ${session.title ?? ''}`.toLowerCase(),
    });
  }
  if (session.has_summary && session.summary_path) {
    const docType = 'summary' as const;
    const path = session.summary_path;
    const label = `${creatorName} · ${base} · 摘要`;
    rows.push({
      rowKey: `${session.creator_id}:${itemId}:${docType}`,
      creatorId: session.creator_id,
      creatorName,
      sessionKind: session.kind,
      itemId,
      docType,
      path,
      label,
      searchText: `${creatorName} ${base} 摘要 ${session.title ?? ''}`.toLowerCase(),
    });
  }
  return rows;
}

export function filterMentionRows(
  rows: MentionDocumentRow[],
  query: string,
): MentionDocumentRow[] {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((row) => row.searchText.includes(q) || row.label.toLowerCase().includes(q));
}

export function mentionRowToAttachment(row: MentionDocumentRow): ContextAttachment {
  return {
    id: attachmentId(row.docType, row.path),
    docType: row.docType,
    path: row.path,
    label: row.label.split(' · ').slice(1).join(' · ') || row.label,
    creatorId: row.creatorId,
    creatorName: row.creatorName,
    sessionKind: row.sessionKind,
    itemId: row.itemId,
    source: 'mention',
  };
}

/** Extract @mention query ending at caret; returns null if not in mention mode. */
export function parseMentionAtCaret(text: string, caret: number): { start: number; query: string } | null {
  const before = text.slice(0, caret);
  const at = before.lastIndexOf('@');
  if (at < 0) return null;
  const segment = before.slice(at + 1);
  if (/\s/.test(segment)) return null;
  return { start: at, query: segment };
}

export function removeMentionSegment(text: string, start: number, caret: number): string {
  return `${text.slice(0, start)}${text.slice(caret)}`;
}
