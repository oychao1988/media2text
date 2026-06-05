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
import { buildWsUrl } from '../../lib/api';
import type { WsEvent } from '../../lib/types';

const MIN_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30000;

type EventsContextValue = {
  subscribe: (listener: (event: WsEvent) => void) => () => void;
  onReconnect: (listener: () => void) => () => void;
  connected: boolean;
};

const EventsContext = createContext<EventsContextValue | null>(null);

type ProviderProps = {
  children: ReactNode;
  enabled?: boolean;
};

export function EventsProvider({ children, enabled = true }: ProviderProps) {
  const listenersRef = useRef(new Set<(event: WsEvent) => void>());
  const reconnectRef = useRef(new Set<() => void>());
  const [connected, setConnected] = useState(false);

  const subscribe = useCallback((listener: (event: WsEvent) => void) => {
    listenersRef.current.add(listener);
    return () => listenersRef.current.delete(listener);
  }, []);

  const onReconnect = useCallback((listener: () => void) => {
    reconnectRef.current.add(listener);
    return () => reconnectRef.current.delete(listener);
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;

    let ws: WebSocket | null = null;
    let disposed = false;
    let attempt = 0;
    let reconnectTimer: number | undefined;

    const notifyReconnect = () => {
      for (const fn of reconnectRef.current) fn();
    };

    const scheduleReconnect = () => {
      if (disposed) return;
      setConnected(false);
      const delay = Math.min(MIN_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS);
      attempt += 1;
      reconnectTimer = window.setTimeout(() => {
        notifyReconnect();
        void connect();
      }, delay);
    };

    const connect = async () => {
      if (disposed) return;
      try {
        const url = await buildWsUrl('/api/events');
        ws = new WebSocket(url);
      } catch {
        scheduleReconnect();
        return;
      }

      ws.onopen = () => {
        attempt = 0;
        setConnected(true);
      };

      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(String(ev.data)) as WsEvent;
          if (data.type === 'ping') return;
          for (const listener of listenersRef.current) listener(data);
        } catch {
          /* ignore malformed */
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (!disposed) scheduleReconnect();
      };

      ws.onerror = () => {
        ws?.close();
      };
    };

    void connect();

    return () => {
      disposed = true;
      setConnected(false);
      if (reconnectTimer != null) window.clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [enabled]);

  const value = useMemo(
    () => ({ subscribe, onReconnect, connected }),
    [subscribe, onReconnect, connected],
  );

  return <EventsContext.Provider value={value}>{children}</EventsContext.Provider>;
}

export function useEvents(): EventsContextValue {
  const ctx = useContext(EventsContext);
  if (!ctx) throw new Error('useEvents must be used within EventsProvider');
  return ctx;
}

/** @deprecated Prefer EventsProvider + useEvents(). Kept for tests. */
export function useEventsWs(options: {
  enabled?: boolean;
  onEvent?: (event: WsEvent) => void;
  onReconnect?: () => void;
}): void {
  const { subscribe, onReconnect } = useEvents();
  const { enabled = true, onEvent, onReconnect: onReconnectCb } = options;

  useEffect(() => {
    if (!enabled || !onEvent) return undefined;
    return subscribe(onEvent);
  }, [enabled, onEvent, subscribe]);

  useEffect(() => {
    if (!enabled || !onReconnectCb) return undefined;
    return onReconnect(onReconnectCb);
  }, [enabled, onReconnectCb, onReconnect]);
}
