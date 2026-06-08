import type { ContextAttachment } from './contextAttachment';

export type AgentContext = {
  creatorId?: string;
  sessionId?: string;
  threadId?: string;
  sessionKind?: 'live' | 'vod' | null;
  transcriptPath?: string | null;
  summaryPath?: string | null;
  contextMode?: 'transcript' | 'summary' | 'both';
  attachments?: ContextAttachment[];
};

export type ActivateThreadPayload = {
  creatorId?: string;
  sessionId?: string;
  sessionKind?: 'live' | 'vod' | null;
  transcriptPath?: string | null;
  summaryPath?: string | null;
  contextMode?: 'transcript' | 'summary' | 'both';
  clearSession?: boolean;
  attachments?: ContextAttachment[];
};

export function buildActivatePayload(ctx: AgentContext): ActivateThreadPayload {
  const payload: ActivateThreadPayload = {
    contextMode: ctx.contextMode,
  };
  if (ctx.creatorId) payload.creatorId = ctx.creatorId;
  if (ctx.sessionId) {
    payload.sessionId = ctx.sessionId;
  } else if (ctx.sessionId === null) {
    payload.clearSession = true;
  }
  if (ctx.sessionKind !== undefined) payload.sessionKind = ctx.sessionKind;
  if (ctx.transcriptPath !== undefined) payload.transcriptPath = ctx.transcriptPath;
  if (ctx.summaryPath !== undefined) payload.summaryPath = ctx.summaryPath;
  if (ctx.attachments !== undefined) payload.attachments = ctx.attachments;
  return payload;
}
