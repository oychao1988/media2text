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

## 行为准则
1. 涉及具体场次正文时，优先调用 m2t_read_transcript / m2t_read_summary / m2t_read_manifest，不要编造转写内容。
2. 写操作（录制、守护进程）前用一句话确认博主与操作类型。
3. 列表过长时摘要前几条并提示缩小范围。
4. 出错时用简体中文说明原因与可操作建议。
5. 所有业务操作仅通过 m2t_* 工具访问本地 API（{api_base_url}），不要假设可直接读写磁盘业务文件。`;

export function buildSystemPrompt(ctx: RuntimeContext): string {
  return SYSTEM_PROMPT_TEMPLATE.replace('{workspace}', ctx.workspace || '—')
    .replace('{creator_name}', ctx.creatorName ?? '（未选择）')
    .replace('{creator_id}', ctx.creatorId || '—')
    .replace('{platform}', ctx.creatorPlatform ?? '—')
    .replace('{session_id}', ctx.sessionId || '（无）')
    .replace('{session_started}', ctx.sessionStartedAt ?? '—')
    .replace('{transcript_path}', ctx.transcriptPath ?? '（未知，请用工具读取）')
    .replace('{summary_path}', ctx.summaryPath ?? '（未知，请用工具读取）')
    .replace('{api_base_url}', ctx.apiBaseUrl);
}

export function createInitialContext(): RuntimeContext {
  return {
    ...readEnvContext(),
    creatorName: null,
    creatorPlatform: null,
    sessionStartedAt: null,
    transcriptPath: null,
    summaryPath: null,
  };
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
  if (ctx.sessionId) {
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
