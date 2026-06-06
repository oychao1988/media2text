import { useCallback, useEffect, useRef, useState } from 'react';
import type { PiEvent, PiUserMessagePayload } from '@m2t/shared';
import { apiGet, apiPatch, apiPost } from '../../lib/api';
import {
  flushPendingAgentReload,
  onAgentSidecarLifecycle,
  sendAgentContextRefresh,
  sendAgentUserMessage,
  startAgentSidecar,
} from './agentSidecar';
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

export type AgentStatus = 'starting' | 'ready' | 'crashed' | 'error';

export type SessionContext = {
  sessionId: string | null;
  sessionKind?: 'live' | 'vod' | null;
  transcriptPath?: string | null;
  summaryPath?: string | null;
  contextMode?: 'transcript' | 'summary' | 'both';
};

export function useM2tAgent(opts: {
  threadId: string | null;
  creatorId: string | null;
  sessionContext: SessionContext;
}) {
  const { threadId, creatorId, sessionContext } = opts;
  const [status, setStatus] = useState<AgentStatus>('starting');
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [threadModel, setThreadModel] = useState<string>('auto');
  const [providers, setProviders] = useState<ChatProvider[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeTurn, setActiveTurn] = useState<ActiveTurn | null>(null);
  const pendingUserRef = useRef<ChatMessage | null>(null);
  const pendingAssistantRef = useRef<{
    text: string;
    thinkingText?: string;
    durationMs?: number;
  } | null>(null);

  const persistMessage = useCallback(
    async (
      role: 'user' | 'assistant',
      content: string,
      extra?: { thinkingText?: string; durationMs?: number },
    ) => {
      if (!threadId) return;
      await apiPost(`/api/chat/threads/${threadId}/messages`, {
        role,
        content,
        thinkingText: extra?.thinkingText,
        durationMs: extra?.durationMs,
      });
    },
    [threadId],
  );

  const loadHistory = useCallback(async (tid: string) => {
    const res = await apiGet<{
      messages: Array<{
        id: string;
        role: string;
        content: string;
        thinking_text?: string | null;
        duration_ms?: number | null;
      }>;
    }>(`/api/chat/threads/${tid}/messages`, true);
    const rows: ChatMessage[] = (res.messages ?? []).map((m) => {
      if (m.role === 'user') {
        return { id: m.id, role: 'user' as const, text: m.content, persisted: true };
      }
      return {
        id: m.id,
        role: 'assistant' as const,
        text: m.content,
        thinkingText: m.thinking_text ?? undefined,
        durationMs: m.duration_ms ?? undefined,
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
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const listed = await apiGet<{ threads: Array<{ id: string; model?: string }> }>(
          '/api/chat/threads',
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
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: 'assistant',
            text: `Agent 错误：${event.payload.message}`,
          },
        ]);
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
        pendingAssistantRef.current = { text, durationMs, thinkingText };
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
            },
          ];
        });
        return;
      }
      if (event.type === 'turn.end') {
        setActiveTurn(null);
        void (async () => {
          const userMsg = pendingUserRef.current;
          const assistant = pendingAssistantRef.current;
          pendingUserRef.current = null;
          pendingAssistantRef.current = null;
          if (userMsg?.role === 'user' && !userMsg.persisted) {
            await persistMessage('user', userMsg.text);
          }
          if (assistant) {
            await persistMessage('assistant', assistant.text, {
              thinkingText: assistant.thinkingText,
              durationMs: assistant.durationMs,
            });
          }
          await flushPendingAgentReload();
        })();
        return;
      }
      if (event.type === 'tool.result') {
        setMessages((prev) => [
          ...prev,
          { id: nextId(), role: 'tool', result: { type: 'tool.result', payload: event.payload } },
        ]);
      }
    },
    [persistMessage],
  );

  const handleEventRef = useRef(handleEvent);
  useEffect(() => {
    handleEventRef.current = handleEvent;
  }, [handleEvent]);

  useEffect(() => {
    if (!creatorId) {
      setStatus('error');
      setFatalError('请先选择博主');
      return;
    }

    let cancelled = false;
    let stop: (() => Promise<void>) | undefined;
    setStatus('starting');
    setFatalError(null);

    void startAgentSidecar(
      (ev) => {
        if (!cancelled) handleEventRef.current(ev);
      },
      {
        creatorId: creatorId ?? undefined,
        sessionId: sessionContext.sessionId ?? undefined,
        threadId: threadId ?? undefined,
      },
    )
      .then((s) => {
        stop = s;
      })
      .catch((err) => {
        const msg = err instanceof Error ? err.message : String(err);
        setStatus('error');
        setFatalError(msg || 'Agent sidecar 启动失败');
      });

    return () => {
      cancelled = true;
      void stop?.();
    };
  }, [creatorId, threadId, sessionContext.sessionId]);

  useEffect(() => {
    if (!creatorId || !threadId) return;
    void sendAgentContextRefresh({
      creatorId,
      sessionId: sessionContext.sessionId ?? undefined,
      threadId,
      sessionKind: sessionContext.sessionKind ?? null,
      transcriptPath: sessionContext.transcriptPath ?? null,
      summaryPath: sessionContext.summaryPath ?? null,
      contextMode: sessionContext.contextMode,
    });
  }, [creatorId, threadId, sessionContext]);

  useEffect(() => {
    if (!threadId) return;
    void apiPatch(`/api/chat/threads/${threadId}`, {
      sessionId: sessionContext.sessionId ?? undefined,
      clearSession: sessionContext.sessionId == null,
    }).catch(() => {});
  }, [threadId, sessionContext.sessionId]);

  useEffect(() => {
    return onAgentSidecarLifecycle((phase) => {
      if (phase === 'crashed') setStatus('crashed');
      if (phase === 'recovering') setStatus('starting');
    });
  }, []);

  const patchThreadModel = useCallback(
    async (model: string) => {
      if (!threadId) return;
      setThreadModel(model);
      await apiPatch(`/api/chat/threads/${threadId}`, { model });
    },
    [threadId],
  );

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || status !== 'ready' || !threadId) return;
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

      const userMsg: ChatMessage = { id: nextId(), role: 'user', text: trimmed };
      pendingUserRef.current = userMsg;
      setMessages((prev) => [...prev, userMsg]);
      setActiveTurn({ ...INITIAL_TURN });

      const payload: PiUserMessagePayload = {
        text: trimmed,
        providerId: defaultProvider.name,
        model: threadModel,
      };
      await sendAgentUserMessage(payload);
    },
    [providers, status, threadId, threadModel],
  );

  return {
    ready: status === 'ready' && Boolean(threadId),
    status,
    fatalError,
    messages,
    activeTurn,
    providers,
    threadModel,
    patchThreadModel,
    sendMessage,
  };
}
