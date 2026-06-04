import { useEffect, useRef } from 'react';
import { buildWsUrl } from '../../lib/api';
import type { WsEvent } from '../../lib/types';

const MIN_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30000;

type Options = {
  enabled?: boolean;
  onEvent?: (event: WsEvent) => void;
  onReconnect?: () => void;
};

export function useEventsWs({ enabled = true, onEvent, onReconnect }: Options): void {
  const onEventRef = useRef(onEvent);
  const onReconnectRef = useRef(onReconnect);
  onEventRef.current = onEvent;
  onReconnectRef.current = onReconnect;

  useEffect(() => {
    if (!enabled) return undefined;

    let ws: WebSocket | null = null;
    let disposed = false;
    let attempt = 0;
    let reconnectTimer: number | undefined;

    const scheduleReconnect = () => {
      if (disposed) return;
      const delay = Math.min(MIN_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS);
      attempt += 1;
      reconnectTimer = window.setTimeout(() => {
        onReconnectRef.current?.();
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
      };

      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(String(ev.data)) as WsEvent;
          if (data.type === 'ping') return;
          onEventRef.current?.(data);
        } catch {
          /* ignore malformed */
        }
      };

      ws.onclose = () => {
        if (!disposed) scheduleReconnect();
      };

      ws.onerror = () => {
        ws?.close();
      };
    };

    void connect();

    return () => {
      disposed = true;
      if (reconnectTimer != null) window.clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [enabled]);
}
