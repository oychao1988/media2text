import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { apiGet, apiPost, ApiError } from '../../lib/api';
import { showToast } from '../../lib/toast';
import type { RuntimeStatus } from '../../lib/types';
import { useEvents } from '../events/EventsProvider';
import { mergeRuntimePatch } from './runtimeMerge';

const HTTP_FALLBACK_MS = 60_000;

type RuntimeState = {
  runtime: RuntimeStatus | null;
  loading: boolean;
  /** GET /api/runtime failed (network, 404 stale API, etc.) */
  fetchError: string | null;
  connected: boolean;
  refresh: () => Promise<void>;
  startRuntime: () => Promise<void>;
  stopRuntime: () => Promise<void>;
  restartRuntime: () => Promise<void>;
};

const RuntimeContext = createContext<RuntimeState | null>(null);

type ProviderProps = {
  children: ReactNode;
};

export function RuntimeProvider({ children }: ProviderProps) {
  const { subscribe, onReconnect, connected } = useEvents();
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await apiGet<RuntimeStatus>('/api/runtime', true);
      setRuntime(res);
      setFetchError(null);
    } catch (err) {
      setRuntime(null);
      if (err instanceof ApiError && err.status === 404) {
        setFetchError('本地 API 版本过旧（缺少 /api/runtime），请完全退出并重新打开 Desktop');
      } else {
        setFetchError('无法连接本地 API，请确认 sidecar 已启动');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    return subscribe((event) => {
      if (event.type === 'runtime.health' || event.type === 'queue.updated') {
        setRuntime((prev) => mergeRuntimePatch(prev, event));
      }
    });
  }, [subscribe]);

  useEffect(() => {
    return onReconnect(() => {
      void refresh();
    });
  }, [onReconnect, refresh]);

  useEffect(() => {
    if (connected) return undefined;
    const id = window.setInterval(() => void refresh(), HTTP_FALLBACK_MS);
    return () => window.clearInterval(id);
  }, [connected, refresh]);

  const startRuntime = useCallback(async () => {
    try {
      await apiPost('/api/runtime/start', undefined, true);
      showToast('守护进程已启动', 'success');
      await refresh();
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : '启动失败';
      showToast(msg, 'error');
      throw err;
    }
  }, [refresh]);

  const stopRuntime = useCallback(async () => {
    try {
      await apiPost('/api/runtime/stop', undefined, true);
      showToast('监控已停止', 'success');
      await refresh();
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : '停止失败';
      showToast(msg, 'error');
      throw err;
    }
  }, [refresh]);

  const restartRuntime = useCallback(async () => {
    try {
      await apiPost('/api/runtime/restart', undefined, true);
      showToast('守护进程已重启', 'success');
      await refresh();
    } catch {
      showToast('守护进程重启失败', 'error');
    }
  }, [refresh]);

  const value = useMemo(
    () => ({
      runtime,
      loading,
      fetchError,
      connected,
      refresh,
      startRuntime,
      stopRuntime,
      restartRuntime,
    }),
    [runtime, loading, fetchError, connected, refresh, startRuntime, stopRuntime, restartRuntime],
  );

  return <RuntimeContext.Provider value={value}>{children}</RuntimeContext.Provider>;
}

export function useRuntime(): RuntimeState {
  const ctx = useContext(RuntimeContext);
  if (!ctx) throw new Error('useRuntime must be used within RuntimeProvider');
  return ctx;
}

/** Left rail / shell: monitor considered active when not stopped. */
export function useMonitorActive(): boolean {
  const { runtime, loading } = useRuntime();
  if (loading || !runtime) return false;
  return runtime.health !== 'stopped';
}
