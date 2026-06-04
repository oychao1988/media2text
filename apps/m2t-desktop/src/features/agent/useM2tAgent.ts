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
import type { ActiveTurn, ChatMessage, ChatProvider, ThreadRow } from './types';

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

export function useM2tAgent(opts: {
  creatorId: string | null;
  sessionId: string | null;
}) {
  const { creatorId, sessionId } = opts;
  const [status, setStatus] = useState<AgentStatus>('starting');
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
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

  const ensureThread = useCallback(async (): Promise<string | null> => {
    if (!creatorId) return null;
    if (threadId) return threadId;
    const listed = await apiGet<{ threads: ThreadRow[] }>(
      `/api/chat/threads?creatorId=${encodeURIComponent(creatorId)}${
        sessionId ? `&sessionId=${encodeURIComponent(sessionId)}` : ''
      }`,
      true,
    );
    const existing = listed.threads?.[0];
    if (existing) {
      setThreadId(existing.id);
      setThreadModel(existing.model || 'auto');
      return existing.id;
    }
    const created = await apiPost<{ thread: ThreadRow }>('/api/chat/threads', {
      creatorId,
      sessionId: sessionId ?? undefined,
      title: 'Agent',
      model: 'auto',
      contextMode: 'both',
    });
    setThreadId(created.thread.id);
    setThreadModel(created.thread.model || 'auto');
    return created.thread.id;
  }, [creatorId, sessionId, threadId]);

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
    if (!creatorId) {
      setThreadId(null);
      setMessages([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const tid = await ensureThread();
        if (!tid || cancelled) return;
        await loadHistory(tid);
      } catch {
        if (!cancelled) setMessages([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [creatorId, sessionId, ensureThread, loadHistory]);

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
      { creatorId: creatorId ?? undefined, sessionId: sessionId ?? undefined },
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
  }, [creatorId, sessionId]);

  useEffect(() => {
    if (!creatorId) return;
    void sendAgentContextRefresh({
      creatorId: creatorId ?? undefined,
      sessionId: sessionId ?? undefined,
      threadId: threadId ?? undefined,
    });
  }, [creatorId, sessionId, threadId]);

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
      if (!trimmed || status !== 'ready') return;
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
    [providers, status, threadModel],
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
  };
}
