import { useCallback, useEffect, useState } from 'react';
import { apiDelete, apiGet, apiPatch, apiPost } from '../../lib/api';
import type { ThreadRow } from './types';

export type HistoryFilter = 'all' | 'creator';

export function useAgentThreads(selectedCreatorId: string | null) {
  const [threads, setThreads] = useState<ThreadRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [historyFilter, setHistoryFilter] = useState<HistoryFilter>('all');

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const query =
        historyFilter === 'creator' && selectedCreatorId
          ? `?creatorId=${encodeURIComponent(selectedCreatorId)}`
          : '';
      const res = await apiGet<{ ok: boolean; threads: ThreadRow[] }>(
        `/api/agent/threads${query}`,
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
  }, [historyFilter, selectedCreatorId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createThread = useCallback(
    async (creatorId: string, sessionId?: string | null): Promise<ThreadRow | null> => {
      const res = await apiPost<{ ok: boolean; thread: ThreadRow }>('/api/agent/threads', {
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

  const createGlobalThread = useCallback(async (): Promise<ThreadRow | null> => {
    const res = await apiPost<{ ok: boolean; thread: ThreadRow }>('/api/agent/threads', {
      title: '全局 Agent',
      model: 'auto',
      contextMode: 'both',
    });
    await refresh();
    return res.thread ?? null;
  }, [refresh]);

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

  return {
    threads,
    loading,
    historyFilter,
    setHistoryFilter,
    refresh,
    createThread,
    createGlobalThread,
    renameThread,
    deleteThread,
    patchThreadSession,
  };
}
