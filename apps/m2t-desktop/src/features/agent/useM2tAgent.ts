import { useCallback, useEffect, useRef, useState } from 'react';
import { parsePiEventLine, type PiEvent } from '@m2t/shared';
import { apiGet, apiPatch, apiPost, ApiError, buildWsUrl } from '../../lib/api';
import { showToast } from '../../lib/toast';
import { buildActivatePayload, type AgentContext } from './agentContext';
import { parseToolMessagePayload } from './toolMessagePayload';
import type { ActiveTurn, ChatMessage, ChatProvider } from './types';

const INITIAL_TURN: ActiveTurn = {
  phase: 'preparing',
  phaseLabel: '准备中…',
  thinkingText: '',
  assistantText: '',
};

function nextId(): string {
  return `m-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export type AgentStatus = 'connecting' | 'ready' | 'reconnecting' | 'error';

export type SessionContext = AgentContext;

export function useM2tAgent(opts: {
  threadId: string | null;
  /** Sidebar-selected creator (mismatch checks only). */
  creatorId: string | null;
  /** Thread-bound creator; omit for global threads. */
  threadCreatorId?: string | null;
  sessionContext: SessionContext;
  onTurnEnd?: () => void;
  onThreadTitle?: (threadId: string, title: string) => void;
}) {
  const { threadId, creatorId, threadCreatorId, sessionContext, onTurnEnd, onThreadTitle } = opts;
  const [status, setStatus] = useState<AgentStatus>('connecting');
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [threadModel, setThreadModel] = useState<string>('auto');
  const [providers, setProviders] = useState<ChatProvider[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeTurn, setActiveTurn] = useState<ActiveTurn | null>(null);

  const loadHistory = useCallback(async (tid: string) => {
    const res = await apiGet<{
      messages: Array<{
        id: string;
        role: string;
        content: string;
        tool_name?: string | null;
        toolName?: string | null;
        thinking_text?: string | null;
        duration_ms?: number | null;
        created_at?: string | null;
      }>;
    }>(`/api/agent/threads/${tid}/messages`, true);
    const rows: ChatMessage[] = (res.messages ?? []).map((m) => {
      if (m.role === 'user') {
        return {
          id: m.id,
          role: 'user' as const,
          text: m.content,
          createdAt: m.created_at ?? undefined,
          persisted: true,
        };
      }
      if (m.role === 'tool') {
        const { payload, toolName } = parseToolMessagePayload(
          m.content,
          m.tool_name ?? m.toolName,
        );
        return {
          id: m.id,
          role: 'tool' as const,
          toolName,
          result: { type: 'tool.result' as const, payload },
        };
      }
      return {
        id: m.id,
        role: 'assistant' as const,
        text: m.content,
        thinkingText: m.thinking_text ?? undefined,
        durationMs: m.duration_ms ?? undefined,
        createdAt: m.created_at ?? undefined,
        persisted: true,
      };
    });
    setMessages(rows);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const prov = await apiGet<{ providers: ChatProvider[] }>('/api/chat/providers', true);
        if (!cancelled) setProviders(prov.providers ?? []);
      } catch {
        if (!cancelled) setProviders([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!threadId) {
      setMessages([]);
      setThreadModel('auto');
      setActiveTurn(null);
      setStatus('ready');
      setFatalError(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const listed = await apiGet<{ threads: Array<{ id: string; model?: string }> }>(
          '/api/agent/threads',
          true,
        );
        const row = listed.threads?.find((t) => t.id === threadId);
        if (row?.model && !cancelled) setThreadModel(row.model);
        await loadHistory(threadId);
      } catch {
        if (!cancelled) setMessages([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [threadId, loadHistory]);

  const handleEvent = useCallback(
    (event: PiEvent) => {
      if (event.type === 'sidecar.ready') {
        setStatus('ready');
        setFatalError(null);
        return;
      }
      if (event.type === 'error') {
        setActiveTurn(null);
        showToast(event.payload.message, 'error');
        return;
      }
      if (event.type === 'turn.start') {
        setActiveTurn((prev) => prev ?? { ...INITIAL_TURN });
        return;
      }
      if (event.type === 'turn.phase') {
        const { phase, label } = event.payload;
        setActiveTurn((prev) =>
          prev
            ? { ...prev, phase, phaseLabel: label }
            : { ...INITIAL_TURN, phase, phaseLabel: label },
        );
        return;
      }
      if (event.type === 'message.thinking') {
        setActiveTurn((prev) =>
          prev
            ? { ...prev, thinkingText: event.payload.text, phase: 'thinking', phaseLabel: '思考中…' }
            : {
                ...INITIAL_TURN,
                thinkingText: event.payload.text,
                phase: 'thinking',
                phaseLabel: '思考中…',
              },
        );
        return;
      }
      if (event.type === 'message.assistant.delta') {
        const delta = event.payload.delta;
        setActiveTurn((prev) => {
          const base = prev ?? { ...INITIAL_TURN };
          return {
            ...base,
            assistantText: base.assistantText + delta,
            phase: 'composing',
            phaseLabel: '生成回复…',
          };
        });
        return;
      }
      if (event.type === 'message.assistant') {
        const { text, durationMs, thinkingText } = event.payload;
        setActiveTurn(null);
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === 'assistant' && last.text === text) return prev;
          return [
            ...prev,
            {
              id: nextId(),
              role: 'assistant',
              text,
              durationMs,
              thinkingText,
              createdAt: new Date().toISOString(),
            },
          ];
        });
        return;
      }
      if (event.type === 'turn.end') {
        setActiveTurn(null);
        if (threadId) void loadHistory(threadId);
        onTurnEnd?.();
        return;
      }
      if (event.type === 'thread.title') {
        onThreadTitle?.(event.payload.threadId, event.payload.title);
        return;
      }
      if (event.type === 'approval.request') {
        const { id, action, summary } = event.payload;
        const ok = window.confirm(`Agent 请求确认：${action}\n\n${summary}`);
        void apiPost(`/api/agent/approvals/${encodeURIComponent(id)}`, { approved: ok }, true).catch(
          () => {
            showToast('无法提交确认结果', 'error');
          },
        );
        return;
      }
      if (event.type === 'tool.result') {
        const { name, ...payload } = event.payload;
        const toolName = typeof name === 'string' ? name : undefined;
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: 'tool',
            toolName,
            result: { type: 'tool.result', payload },
          },
        ]);
      }
    },
    [loadHistory, onThreadTitle, onTurnEnd, threadId],
  );

  const handleEventRef = useRef(handleEvent);
  useEffect(() => {
    handleEventRef.current = handleEvent;
  }, [handleEvent]);

  useEffect(() => {
    if (!threadId) return;

    let cancelled = false;
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = async () => {
      if (cancelled) return;
      setStatus((s) => (s === 'ready' ? 'reconnecting' : 'connecting'));
      try {
        const url = await buildWsUrl(
          `/api/agent/stream?threadId=${encodeURIComponent(threadId)}`,
        );
        ws = new WebSocket(url);
        ws.onopen = () => {
          if (!cancelled) setFatalError(null);
        };
        ws.onmessage = (ev) => {
          const line = String(ev.data);
          try {
            const raw = JSON.parse(line) as { type?: string };
            if (raw.type === 'ping') return;
          } catch {
            /* fall through to PiEvent parser */
          }
          const parsed = parsePiEventLine(line);
          if (parsed && !cancelled) handleEventRef.current(parsed);
        };
        ws.onclose = () => {
          if (cancelled) return;
          setStatus('reconnecting');
          reconnectTimer = setTimeout(() => void connect(), 1500);
        };
        ws.onerror = () => {
          if (!cancelled) setStatus('reconnecting');
        };
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        if (!cancelled) {
          setStatus('error');
          setFatalError(msg || 'Agent WebSocket 连接失败');
        }
      }
    };

    void connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [threadId]);

  useEffect(() => {
    if (!threadId) return;
    const payload = buildActivatePayload({
      creatorId: threadCreatorId ?? undefined,
      sessionId: sessionContext.sessionId ?? null,
      threadId,
      sessionKind: sessionContext.sessionKind ?? null,
      transcriptPath: sessionContext.transcriptPath ?? null,
      summaryPath: sessionContext.summaryPath ?? null,
      contextMode: sessionContext.contextMode,
      attachments: sessionContext.attachments,
    });
    void apiPatch(`/api/agent/threads/${threadId}/activate`, payload, true).catch((err) => {
      const msg = err instanceof ApiError ? err.message : '上下文同步失败';
      showToast(`${msg}，请重试`, 'error');
    });
  }, [threadCreatorId, threadId, sessionContext]);

  const patchThreadModel = useCallback(
    async (model: string, providerName?: string | null) => {
      const previous = threadModel;
      setThreadModel(model);
      if (!threadId) return;
      try {
        await apiPatch(`/api/agent/threads/${threadId}`, {
          model,
          ...(providerName ? { providerName } : {}),
        });
      } catch (err) {
        setThreadModel(previous);
        const msg = err instanceof ApiError ? err.message : '模型切换失败';
        showToast(msg, 'error');
      }
    },
    [threadId, threadModel],
  );

  const sendMessage = useCallback(
    async (text: string, overrideThreadId?: string) => {
      const trimmed = text.trim();
      const tid = overrideThreadId ?? threadId;
      if (!trimmed || status !== 'ready' || !tid) return;
      const defaultProvider = providers.find((p) => p.configured) ?? providers[0];
      if (!defaultProvider) {
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: 'assistant',
            text: '请先在系统配置 · AI 段添加 LLM Provider 并配置 .env API Key。',
          },
        ]);
        return;
      }

      const userMsg: ChatMessage = {
        id: nextId(),
        role: 'user',
        text: trimmed,
        createdAt: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setActiveTurn({ ...INITIAL_TURN });

      try {
        await apiPost(
          `/api/agent/threads/${tid}/turn`,
          {
            text: trimmed,
            sidebarCreatorId: creatorId ?? undefined,
          },
          true,
        );
      } catch (err) {
        setActiveTurn(null);
        setMessages((prev) => prev.filter((m) => m.id !== userMsg.id));
        const msg = err instanceof Error ? err.message : '发送失败';
        showToast(msg, 'error');
      }
    },
    [creatorId, providers, status, threadId],
  );

  const retryMessage = useCallback(
    async (messageId: string, text: string) => {
      const trimmed = text.trim();
      const tid = threadId;
      if (!trimmed || status !== 'ready' || !tid || messageId.startsWith('m-')) return;

      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.id === messageId);
        if (idx < 0) return prev;
        return prev.slice(0, idx + 1);
      });
      setActiveTurn({ ...INITIAL_TURN });

      try {
        await apiPost(
          `/api/agent/threads/${tid}/turn`,
          {
            text: trimmed,
            sidebarCreatorId: creatorId ?? undefined,
            retry: true,
            afterMessageId: messageId,
          },
          true,
        );
      } catch (err) {
        setActiveTurn(null);
        const msg = err instanceof Error ? err.message : '重试失败';
        showToast(msg, 'error');
        if (threadId) void loadHistory(threadId);
      }
    },
    [creatorId, loadHistory, status, threadId],
  );

  return {
    ready: status === 'ready',
    status,
    fatalError,
    messages,
    activeTurn,
    providers,
    threadModel,
    patchThreadModel,
    sendMessage,
    retryMessage,
  };
}
