export type ContextAttachmentDocType = 'transcript' | 'summary';

export type ContextAttachment = {
  id: string;
  docType: ContextAttachmentDocType;
  path: string;
  label: string;
  creatorId: string;
  creatorName: string;
  sessionKind: 'live' | 'vod';
  itemId: string;
  source?: 'session' | 'mention';
};

export type ContextMode = 'transcript' | 'summary' | 'both';

export type RuntimeContext = {
  apiBaseUrl: string;
  workspace: string;
  creatorId: string;
  sessionId: string;
  threadId: string;
  creatorName: string | null;
  creatorPlatform: string | null;
  sessionStartedAt: string | null;
  transcriptPath: string | null;
  summaryPath: string | null;
  contextMode: ContextMode;
  attachments: ContextAttachment[];
};

export type ContextRefreshPayload = {
  creatorId?: string | null;
  sessionId?: string | null;
  threadId?: string | null;
  sessionKind?: 'live' | 'vod' | null;
  transcriptPath?: string | null;
  summaryPath?: string | null;
  contextMode?: ContextMode | null;
  attachments?: ContextAttachment[] | null;
};

export function readEnvContext(): Pick<
  RuntimeContext,
  'apiBaseUrl' | 'workspace' | 'creatorId' | 'sessionId' | 'threadId'
> {
  return {
    apiBaseUrl: process.env.M2T_API_BASE_URL?.trim() || 'http://127.0.0.1:8765',
    workspace: process.env.M2T_WORKSPACE?.trim() || './data',
    creatorId: process.env.M2T_CREATOR_ID?.trim() || '',
    sessionId: process.env.M2T_SESSION_ID?.trim() || '',
    threadId: process.env.M2T_THREAD_ID?.trim() || '',
  };
}

const COMPLIANCE = `本工具为个人研究档案工具，用于本地录制、转写与检索复盘，不构成投资咨询，不提供荐股、跟单或买卖建议。`;

const SYSTEM_PROMPT_TEMPLATE = `你是 media2text 桌面端的直播档案助手，帮助用户查看监控状态、录制直播、阅读转写与摘要。

## 合规
${COMPLIANCE}

## 当前上下文
- 工作区：{workspace}
- 博主：{creator_name}（id: {creator_id}，平台: {platform}）
- 场次：{session_id}（开始: {session_started}）
- 转写路径：{transcript_path}
- 摘要路径：{summary_path}
{attachments_block}

## 行为准则
1. 涉及具体场次正文时，优先调用 m2t_read_transcript / m2t_read_summary / m2t_read_manifest，不要编造转写内容。
2. 写操作（录制、守护进程）前用一句话确认博主与操作类型。
3. 列表过长时摘要前几条并提示缩小范围。
4. 出错时用简体中文说明原因与可操作建议。
5. 所有业务操作仅通过 m2t_* 工具访问本地 API（{api_base_url}），不要假设可直接读写磁盘业务文件。`;

function docTypeOf(item: ContextAttachment): string {
  return item.docType;
}

export function filterAttachmentsByContextMode(
  attachments: ContextAttachment[],
  contextMode: ContextMode,
): ContextAttachment[] {
  if (contextMode === 'both') return attachments;
  return attachments.filter((a) => docTypeOf(a) === contextMode);
}

export function formatAttachmentsBlock(
  attachments: ContextAttachment[],
  contextMode: ContextMode,
): string {
  const filtered = filterAttachmentsByContextMode(attachments, contextMode);
  if (filtered.length === 0) return '';
  const lines = ['', '## 附加文档'];
  for (const item of filtered) {
    const docLabel = item.docType === 'transcript' ? '转写' : '摘要';
    const prefix = item.creatorName ? `${item.creatorName} · ` : '';
    lines.push(`- [${docLabel}] ${prefix}${item.label} (${item.path})`);
  }
  return lines.join('\n');
}

export function buildSystemPrompt(ctx: RuntimeContext): string {
  const attachmentsBlock = formatAttachmentsBlock(ctx.attachments, ctx.contextMode);
  return SYSTEM_PROMPT_TEMPLATE.replace('{workspace}', ctx.workspace || '—')
    .replace('{creator_name}', ctx.creatorName ?? '（未选择）')
    .replace('{creator_id}', ctx.creatorId || '—')
    .replace('{platform}', ctx.creatorPlatform ?? '—')
    .replace('{session_id}', ctx.sessionId || '（无）')
    .replace('{session_started}', ctx.sessionStartedAt ?? '—')
    .replace('{transcript_path}', ctx.transcriptPath ?? '（未知，请用工具读取）')
    .replace('{summary_path}', ctx.summaryPath ?? '（未知，请用工具读取）')
    .replace('{attachments_block}', attachmentsBlock)
    .replace('{api_base_url}', ctx.apiBaseUrl);
}

export function createInitialContext(): RuntimeContext {
  return {
    ...readEnvContext(),
    ...readRefreshPathsFromEnv(),
    ...readRefreshAttachmentsFromEnv(),
    creatorName: null,
    creatorPlatform: null,
    sessionStartedAt: null,
    contextMode: readContextModeFromEnv(),
  };
}

export function readContextModeFromEnv(): ContextMode {
  const raw = process.env.M2T_CONTEXT_MODE?.trim();
  if (raw === 'transcript' || raw === 'summary' || raw === 'both') return raw;
  return 'both';
}

export function readRefreshAttachmentsFromEnv(): Pick<RuntimeContext, 'attachments'> {
  const raw = process.env.M2T_ATTACHMENTS?.trim();
  if (!raw) return { attachments: [] };
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return { attachments: [] };
    const attachments = parsed.filter(
      (item): item is ContextAttachment =>
        item != null &&
        typeof item === 'object' &&
        typeof (item as ContextAttachment).path === 'string' &&
        ((item as ContextAttachment).docType === 'transcript' ||
          (item as ContextAttachment).docType === 'summary'),
    );
    return { attachments };
  } catch {
    return { attachments: [] };
  }
}

export function readRefreshPathsFromEnv(): Pick<RuntimeContext, 'transcriptPath' | 'summaryPath'> {
  const transcriptPath = process.env.M2T_TRANSCRIPT_PATH?.trim() || null;
  const summaryPath = process.env.M2T_SUMMARY_PATH?.trim() || null;
  return { transcriptPath, summaryPath };
}

export function applyRefreshPayload(ctx: RuntimeContext, payload: ContextRefreshPayload): void {
  if (payload.creatorId != null) {
    const value = String(payload.creatorId);
    process.env.M2T_CREATOR_ID = value;
    ctx.creatorId = value;
  }
  if (payload.sessionId != null) {
    const value = String(payload.sessionId);
    process.env.M2T_SESSION_ID = value;
    ctx.sessionId = value;
  }
  if (payload.threadId != null) {
    const value = String(payload.threadId);
    process.env.M2T_THREAD_ID = value;
    ctx.threadId = value;
  }
  if ('sessionKind' in payload) {
    if (payload.sessionKind != null) {
      process.env.M2T_SESSION_KIND = String(payload.sessionKind);
    } else {
      delete process.env.M2T_SESSION_KIND;
    }
  }
  if ('contextMode' in payload) {
    if (payload.contextMode != null) {
      process.env.M2T_CONTEXT_MODE = String(payload.contextMode);
      ctx.contextMode = payload.contextMode;
    } else {
      delete process.env.M2T_CONTEXT_MODE;
      ctx.contextMode = 'both';
    }
  }
  if ('transcriptPath' in payload) {
    if (payload.transcriptPath != null) {
      const value = String(payload.transcriptPath);
      process.env.M2T_TRANSCRIPT_PATH = value;
      ctx.transcriptPath = value;
    } else {
      delete process.env.M2T_TRANSCRIPT_PATH;
      ctx.transcriptPath = null;
    }
  }
  if ('summaryPath' in payload) {
    if (payload.summaryPath != null) {
      const value = String(payload.summaryPath);
      process.env.M2T_SUMMARY_PATH = value;
      ctx.summaryPath = value;
    } else {
      delete process.env.M2T_SUMMARY_PATH;
      ctx.summaryPath = null;
    }
  }
  if ('attachments' in payload) {
    if (payload.attachments == null) {
      // omit / null — do not modify attachments
    } else if (Array.isArray(payload.attachments)) {
      const json = JSON.stringify(payload.attachments);
      process.env.M2T_ATTACHMENTS = json;
      ctx.attachments = payload.attachments;
    } else {
      delete process.env.M2T_ATTACHMENTS;
      ctx.attachments = [];
    }
  }
}

export async function hydrateContextFromApi(ctx: RuntimeContext): Promise<void> {
  const base = ctx.apiBaseUrl.replace(/\/$/, '');
  if (ctx.creatorId) {
    try {
      const res = await fetch(`${base}/api/creators/${encodeURIComponent(ctx.creatorId)}`);
      if (res.ok) {
        const body = (await res.json()) as {
          creator?: { display_name?: string; platform?: string };
        };
        ctx.creatorName = body.creator?.display_name ?? null;
        ctx.creatorPlatform = body.creator?.platform ?? null;
      }
    } catch {
      // API 不可达时不阻断对话
    }
  }
  if (ctx.sessionId && !ctx.transcriptPath && !ctx.summaryPath) {
    try {
      const res = await fetch(`${base}/api/sessions/${encodeURIComponent(ctx.sessionId)}`);
      if (res.ok) {
        const body = (await res.json()) as {
          session?: {
            started_at?: string;
            paths?: { transcript_path?: string; summary_path?: string };
          };
        };
        ctx.sessionStartedAt = body.session?.started_at ?? null;
        ctx.transcriptPath = body.session?.paths?.transcript_path ?? null;
        ctx.summaryPath = body.session?.paths?.summary_path ?? null;
      }
    } catch {
      // ignore
    }
  }
}
