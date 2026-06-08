export type ContextAttachmentDocType = 'transcript' | 'summary';

export type ContextAttachmentSource = 'session' | 'mention';

export type ContextAttachment = {
  id: string;
  docType: ContextAttachmentDocType;
  path: string;
  label: string;
  creatorId: string;
  creatorName: string;
  sessionKind: 'live' | 'vod';
  itemId: string;
  sizeBytes?: number;
  source: ContextAttachmentSource;
};

export type SessionDocumentsOffer = {
  sessionId: string;
  sessionKind: 'live' | 'vod';
  creatorId: string;
  creatorName: string;
  itemId: string;
  label: string;
  hasTranscript: boolean;
  hasSummary: boolean;
  transcriptPath?: string | null;
  summaryPath?: string | null;
};

export type ContextMode = 'transcript' | 'summary' | 'both';
