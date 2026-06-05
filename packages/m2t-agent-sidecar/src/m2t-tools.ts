import { defineTool } from '@earendil-works/pi-coding-agent';
import type { ToolResultPayload } from '@m2t/shared';
import { Type } from 'typebox';
import type { RuntimeContext } from './context.js';
import { emitToolResult } from './emit.js';
import { M2tApiClient } from './m2t-api.js';

function toolResultText(result: ToolResultPayload): string {
  if (result.ok) return JSON.stringify(result.data ?? {}, null, 2);
  return result.error?.message ?? '操作失败';
}

function wrapExecute(run: () => Promise<ToolResultPayload>) {
  return async () => {
    const result = await run();
    emitToolResult(result);
    return {
      content: [{ type: 'text' as const, text: toolResultText(result) }],
      details: result,
    };
  };
}

export function createM2tClient(ctx: RuntimeContext): M2tApiClient {
  return new M2tApiClient({ baseUrl: ctx.apiBaseUrl });
}

export function createM2tTools(client: M2tApiClient, ctx: RuntimeContext) {
  const creatorId = () => ctx.creatorId;

  return [
    defineTool({
      name: 'm2t_get_live_status',
      label: 'Live Status',
      description: '查询直播/录制/后处理队列状态',
      parameters: Type.Object({
        creator_id: Type.Optional(Type.String({ description: '博主 id，默认当前上下文' })),
      }),
      async execute(_id, params) {
        const cid = params.creator_id ?? creatorId();
        if (cid) {
          return wrapExecute(() =>
            client.request('GET', `/api/live/status?creator=${encodeURIComponent(cid)}`),
          )();
        }
        return wrapExecute(() => client.request('GET', '/api/runtime'))();
      },
    }),
    defineTool({
      name: 'm2t_list_creators',
      label: 'List Creators',
      description: '列出已登记或监控中的博主',
      parameters: Type.Object({
        all: Type.Optional(Type.Boolean({ description: 'true=全部，false=仅监控' })),
      }),
      async execute(_id, params) {
        const q = params.all ? '?all=1' : '';
        return wrapExecute(() => client.request('GET', `/api/creators${q}`))();
      },
    }),
    defineTool({
      name: 'm2t_get_creator',
      label: 'Get Creator',
      description: '获取博主详情',
      parameters: Type.Object({
        creator_id: Type.String({ description: '博主 id' }),
      }),
      async execute(_id, params) {
        return wrapExecute(() =>
          client.request('GET', `/api/creators/${encodeURIComponent(params.creator_id)}`),
        )();
      },
    }),
    defineTool({
      name: 'm2t_start_recording',
      label: 'Start Recording',
      description: '对博主开始手动录制',
      parameters: Type.Object({
        creator_id: Type.Optional(Type.String()),
      }),
      async execute(_id, params) {
        const cid = params.creator_id ?? creatorId();
        if (!cid) {
          const err: ToolResultPayload = {
            ok: false,
            error: { code: 'MISSING_CREATOR', message: '未指定 creator_id' },
          };
          return wrapExecute(async () => err)();
        }
        return wrapExecute(() =>
          client.request('POST', `/api/creators/${encodeURIComponent(cid)}/recording/start`),
        )();
      },
    }),
    defineTool({
      name: 'm2t_stop_recording',
      label: 'Stop Recording',
      description: '停止博主当前录制',
      parameters: Type.Object({
        creator_id: Type.Optional(Type.String()),
      }),
      async execute(_id, params) {
        const cid = params.creator_id ?? creatorId();
        if (!cid) {
          const err: ToolResultPayload = {
            ok: false,
            error: { code: 'MISSING_CREATOR', message: '未指定 creator_id' },
          };
          return wrapExecute(async () => err)();
        }
        return wrapExecute(() =>
          client.request('POST', `/api/creators/${encodeURIComponent(cid)}/recording/stop`),
        )();
      },
    }),
    defineTool({
      name: 'm2t_daemon_start',
      label: 'Daemon Start',
      description: '启动 monitor watch 守护进程',
      parameters: Type.Object({}),
      async execute() {
        return wrapExecute(() => client.request('POST', '/api/runtime/start'))();
      },
    }),
    defineTool({
      name: 'm2t_daemon_stop',
      label: 'Daemon Stop',
      description: '停止 monitor watch 守护进程',
      parameters: Type.Object({}),
      async execute() {
        return wrapExecute(() => client.request('POST', '/api/runtime/stop'))();
      },
    }),
    defineTool({
      name: 'm2t_post_process_run',
      label: 'Post Process Run',
      description: '消化直播后处理队列',
      parameters: Type.Object({
        limit: Type.Optional(Type.Number({ description: '最多处理条数，默认 10' })),
      }),
      async execute(_id, params) {
        return wrapExecute(() =>
          client.request('POST', '/api/post-process/run', {
            limit: params.limit ?? 10,
          }),
        )();
      },
    }),
    defineTool({
      name: 'm2t_pipeline_run',
      label: 'Pipeline Run',
      description: '异步入队博主作品 sync+download+transcribe 流水线',
      parameters: Type.Object({
        creator_id: Type.Optional(Type.String()),
      }),
      async execute(_id, params) {
        const cid = params.creator_id ?? creatorId();
        if (!cid) {
          const err: ToolResultPayload = {
            ok: false,
            error: { code: 'MISSING_CREATOR', message: '未指定 creator_id' },
          };
          return wrapExecute(async () => err)();
        }
        return wrapExecute(() =>
          client.request('POST', `/api/creators/${encodeURIComponent(cid)}/pipeline/run`),
        )();
      },
    }),
    defineTool({
      name: 'm2t_read_transcript',
      label: 'Read Transcript',
      description: '读取场次转写',
      parameters: Type.Object({
        session_id: Type.String({ description: 'live session id' }),
      }),
      async execute(_id, params) {
        return wrapExecute(() =>
          client.request('GET', `/api/sessions/${encodeURIComponent(params.session_id)}/transcript`),
        )();
      },
    }),
    defineTool({
      name: 'm2t_read_summary',
      label: 'Read Summary',
      description: '读取场次摘要 markdown',
      parameters: Type.Object({
        session_id: Type.String({ description: 'live session id' }),
      }),
      async execute(_id, params) {
        return wrapExecute(() =>
          client.request('GET', `/api/sessions/${encodeURIComponent(params.session_id)}/summary`),
        )();
      },
    }),
    defineTool({
      name: 'm2t_read_manifest',
      label: 'Read Manifest',
      description: '读取博主 agent-manifest.json',
      parameters: Type.Object({
        creator_id: Type.Optional(Type.String()),
      }),
      async execute(_id, params) {
        const cid = params.creator_id ?? creatorId();
        if (!cid) {
          const err: ToolResultPayload = {
            ok: false,
            error: { code: 'MISSING_CREATOR', message: '未指定 creator_id' },
          };
          return wrapExecute(async () => err)();
        }
        return wrapExecute(() =>
          client.request('GET', `/api/creators/${encodeURIComponent(cid)}/manifest`),
        )();
      },
    }),
    defineTool({
      name: 'm2t_list_sessions',
      label: 'List Sessions',
      description: '列出博主历史直播场次',
      parameters: Type.Object({
        creator_id: Type.Optional(Type.String()),
        limit: Type.Optional(Type.Number()),
      }),
      async execute(_id, params) {
        const cid = params.creator_id ?? creatorId();
        if (!cid) {
          const err: ToolResultPayload = {
            ok: false,
            error: { code: 'MISSING_CREATOR', message: '未指定 creator_id' },
          };
          return wrapExecute(async () => err)();
        }
        const limit = params.limit ?? 20;
        return wrapExecute(() =>
          client.request(
            'GET',
            `/api/creators/${encodeURIComponent(cid)}/sessions?limit=${limit}`,
          ),
        )();
      },
    }),
  ];
}

export function m2tToolNames(): string[] {
  return [
    'm2t_get_live_status',
    'm2t_list_creators',
    'm2t_get_creator',
    'm2t_start_recording',
    'm2t_stop_recording',
    'm2t_daemon_start',
    'm2t_daemon_stop',
    'm2t_post_process_run',
    'm2t_pipeline_run',
    'm2t_read_transcript',
    'm2t_read_summary',
    'm2t_read_manifest',
    'm2t_list_sessions',
  ];
}
