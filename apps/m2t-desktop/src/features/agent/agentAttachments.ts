import type {
  ContextAttachment,
  ContextAttachmentDocType,
  ContextMode,
  SessionDocumentsOffer,
} from './contextAttachment';

export function attachmentId(docType: ContextAttachmentDocType, path: string): string {
  return `${docType}:${path}`;
}

export function dedupeByPath(attachments: ContextAttachment[]): ContextAttachment[] {
  const seen = new Set<string>();
  const out: ContextAttachment[] = [];
  for (const item of attachments) {
    if (seen.has(item.path)) continue;
    seen.add(item.path);
    out.push(item);
  }
  return out;
}

export type LegacyBindingInput = {
  transcriptPath?: string | null;
  summaryPath?: string | null;
  creatorId?: string;
  creatorName?: string;
  sessionKind?: 'live' | 'vod' | null;
  itemId?: string;
  attachments?: ContextAttachment[] | null;
};

export function legacyBindingToAttachments(input: LegacyBindingInput): ContextAttachment[] {
  if (input.attachments?.length) {
    return dedupeByPath(input.attachments);
  }
  const creatorId = input.creatorId ?? '';
  const creatorName = input.creatorName ?? '';
  const sessionKind = input.sessionKind ?? 'live';
  const itemId = input.itemId ?? '';
  const out: ContextAttachment[] = [];
  if (input.transcriptPath) {
    out.push({
      id: attachmentId('transcript', input.transcriptPath),
      docType: 'transcript',
      path: input.transcriptPath,
      label: basename(input.transcriptPath),
      creatorId,
      creatorName,
      sessionKind,
      itemId,
      source: 'session',
    });
  }
  if (input.summaryPath) {
    out.push({
      id: attachmentId('summary', input.summaryPath),
      docType: 'summary',
      path: input.summaryPath,
      label: basename(input.summaryPath),
      creatorId,
      creatorName,
      sessionKind,
      itemId,
      source: 'session',
    });
  }
  return out;
}

export function filterByContextMode(
  attachments: ContextAttachment[],
  mode: ContextMode,
): ContextAttachment[] {
  if (mode === 'both') return attachments;
  return attachments.filter((a) => a.docType === mode);
}

export function attachmentsFromSessionOffer(offer: SessionDocumentsOffer): ContextAttachment[] {
  const out: ContextAttachment[] = [];
  if (offer.hasTranscript && offer.transcriptPath) {
    out.push({
      id: attachmentId('transcript', offer.transcriptPath),
      docType: 'transcript',
      path: offer.transcriptPath,
      label: offer.label,
      creatorId: offer.creatorId,
      creatorName: offer.creatorName,
      sessionKind: offer.sessionKind,
      itemId: offer.itemId,
      source: 'session',
    });
  }
  if (offer.hasSummary && offer.summaryPath) {
    out.push({
      id: attachmentId('summary', offer.summaryPath),
      docType: 'summary',
      path: offer.summaryPath,
      label: offer.label,
      creatorId: offer.creatorId,
      creatorName: offer.creatorName,
      sessionKind: offer.sessionKind,
      itemId: offer.itemId,
      source: 'session',
    });
  }
  return out;
}

function basename(path: string): string {
  const parts = path.split('/');
  return parts[parts.length - 1] ?? path;
}
