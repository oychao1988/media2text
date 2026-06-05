import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { apiGet } from '../../lib/api';
import type { Creator } from '../../lib/types';
import { sortCreatorsLiveFirst } from './creatorUtils';
import { useEventsWs } from './useEventsWs';

type CreatorsState = {
  creators: Creator[];
  loading: boolean;
  error: string | null;
  selectedId: string | null;
  selected: Creator | null;
  /** Bumped after WS/reconnect refresh so live status hooks can re-poll. */
  revision: number;
  refresh: () => Promise<void>;
  setSelectedId: (id: string | null) => void;
};

const CreatorsContext = createContext<CreatorsState | null>(null);

type ProviderProps = {
  children: ReactNode;
  forceEmpty?: boolean;
};

export function CreatorsProvider({ children, forceEmpty }: ProviderProps) {
  const [creators, setCreators] = useState<Creator[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const hasLoadedRef = useRef(false);

  const refresh = useCallback(async () => {
    if (forceEmpty) {
      setCreators([]);
      setLoading(false);
      setError(null);
      hasLoadedRef.current = true;
      return;
    }
    const initial = !hasLoadedRef.current;
    if (initial) setLoading(true);
    setError(null);
    try {
      const res = await apiGet<{ ok: boolean; creators: Creator[] }>('/api/creators', true);
      const list = sortCreatorsLiveFirst(res.creators ?? []);
      setCreators(list);
      setSelectedId((prev) => {
        if (prev && list.some((c) => c.id === prev)) return prev;
        return list[0]?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载博主列表失败');
    } finally {
      hasLoadedRef.current = true;
      setLoading(false);
    }
  }, [forceEmpty]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEventsWs({
    onEvent: () => {
      void refresh().then(() => setRevision((n) => n + 1));
    },
    onReconnect: () => {
      void refresh().then(() => setRevision((n) => n + 1));
    },
  });

  const selected = useMemo(
    () => creators.find((c) => c.id === selectedId) ?? null,
    [creators, selectedId],
  );

  const value = useMemo(
    () => ({
      creators,
      loading,
      error,
      selectedId,
      selected,
      revision,
      refresh,
      setSelectedId,
    }),
    [creators, loading, error, selectedId, selected, revision, refresh],
  );

  return <CreatorsContext.Provider value={value}>{children}</CreatorsContext.Provider>;
}

export function useCreators(): CreatorsState {
  const ctx = useContext(CreatorsContext);
  if (!ctx) throw new Error('useCreators must be used within CreatorsProvider');
  return ctx;
}
