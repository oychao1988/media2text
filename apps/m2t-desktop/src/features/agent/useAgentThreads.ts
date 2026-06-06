import { useCallback, useEffect, useState } from 'react';
import { apiDelete, apiGet, apiPatch, apiPost } from '../../lib/api';
import type { ThreadRow } from './types';

export function useAgentThreads(_selectedCreatorId: string | null) {
  const [threads, setThreads] = useState<ThreadRow[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiGet<{ ok: boolean; threads: ThreadRow[] }>(
        '/api/agent/threads',
        true,
      );
      const rows = (res.threads ?? []).slice().sort((a, b) => {
        const ta = Date.parse(a.updated_at ?? '') || 0;
        const tb = Date.parse(b.updated_at ?? '') || 0;
        return tb - ta;
      });
      setThreads(rows);
    } catch {
      setThreads([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createThread = useCallback(
    async (
      creatorId: string,
      sessionId?: string | null,
      opts?: { model?: string; providerName?: string | null },
    ): Promise<ThreadRow | null> => {
      const res = await apiPost<{ ok: boolean; thread: ThreadRow }>('/api/agent/threads', {
        creatorId,
        sessionId: sessionId ?? undefined,
        title: 'Agent',
        model: opts?.model ?? 'auto',
        providerName: opts?.providerName ?? undefined,
        contextMode: 'both',
      });
      await refresh();
      return res.thread ?? null;
    },
    [refresh],
  );

  const createGlobalThread = useCallback(
    async (opts?: { model?: string; providerName?: string | null }): Promise<ThreadRow | null> => {
      const res = await apiPost<{ ok: boolean; thread: ThreadRow }>('/api/agent/threads', {
        title: '全局 Agent',
        model: opts?.model ?? 'auto',
        providerName: opts?.providerName ?? undefined,
        contextMode: 'both',
      });
      await refresh();
      return res.thread ?? null;
    },
    [refresh],
  );

  const renameThread = useCallback(
    async (threadId: string, title: string) => {
      await apiPatch(`/api/agent/threads/${threadId}`, { title });
      await refresh();
    },
    [refresh],
  );

  const deleteThread = useCallback(
    async (threadId: string) => {
      await apiDelete(`/api/agent/threads/${threadId}`);
      await refresh();
    },
    [refresh],
  );

  const patchThreadSession = useCallback(async (threadId: string, sessionId: string | null) => {
    await apiPatch(`/api/agent/threads/${threadId}`, {
      sessionId: sessionId ?? undefined,
      clearSession: sessionId == null,
    });
  }, []);

  const applyThreadTitle = useCallback((threadId: string, title: string) => {
    setThreads((prev) =>
      prev.map((t) => (t.id === threadId ? { ...t, title } : t)),
    );
  }, []);

  return {
    threads,
    loading,
    refresh,
    createThread,
    createGlobalThread,
    renameThread,
    deleteThread,
    patchThreadSession,
    applyThreadTitle,
  };
}
