import { useCallback, useEffect, useState } from 'react';
import { apiDelete, apiGet, apiPatch, apiPost } from '../../lib/api';
import type { ThreadRow } from './types';

export function useAgentThreads() {
  const [threads, setThreads] = useState<ThreadRow[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiGet<{ ok: boolean; threads: ThreadRow[] }>('/api/chat/threads', true);
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
    async (creatorId: string, sessionId?: string | null): Promise<ThreadRow | null> => {
      const res = await apiPost<{ ok: boolean; thread: ThreadRow }>('/api/chat/threads', {
        creatorId,
        sessionId: sessionId ?? undefined,
        title: 'Agent',
        model: 'auto',
        contextMode: 'both',
      });
      await refresh();
      return res.thread ?? null;
    },
    [refresh],
  );

  const renameThread = useCallback(
    async (threadId: string, title: string) => {
      await apiPatch(`/api/chat/threads/${threadId}`, { title });
      await refresh();
    },
    [refresh],
  );

  const deleteThread = useCallback(
    async (threadId: string) => {
      await apiDelete(`/api/chat/threads/${threadId}`);
      await refresh();
    },
    [refresh],
  );

  const patchThreadSession = useCallback(async (threadId: string, sessionId: string | null) => {
    await apiPatch(`/api/chat/threads/${threadId}`, {
      sessionId: sessionId ?? undefined,
      clearSession: sessionId == null,
    });
  }, []);

  return {
    threads,
    loading,
    refresh,
    createThread,
    renameThread,
    deleteThread,
    patchThreadSession,
  };
}
