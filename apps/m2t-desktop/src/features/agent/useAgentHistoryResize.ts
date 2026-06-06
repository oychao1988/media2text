import { useCallback, useRef, type PointerEvent as ReactPointerEvent } from 'react';
import {
  clamp,
  SIZE_DEFAULTS,
  SIZE_LIMITS,
} from '../layout/layoutConstants';
import { commitLayoutSizes, useLayoutStore } from '../layout/useLayoutStore';

function readCssPx(varName: string, fallback: number): number {
  const v = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(varName));
  return Number.isFinite(v) ? v : fallback;
}

export function useAgentHistoryResize() {
  const dragging = useRef(false);
  const startX = useRef(0);
  const startW = useRef(0);
  const pendingW = useRef(0);

  const onPointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    dragging.current = true;
    startX.current = e.clientX;
    startW.current = readCssPx('--agent-history-w', SIZE_DEFAULTS.agentHistoryW);
    pendingW.current = startW.current;
    e.currentTarget.setPointerCapture(e.pointerId);
    e.currentTarget.classList.add('is-dragging');
    document.body.classList.add('resize-col-active');
  }, []);

  const onPointerMove = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    const dx = e.clientX - startX.current;
    pendingW.current = clamp(
      startW.current - dx,
      SIZE_LIMITS.agentHistory.min,
      SIZE_LIMITS.agentHistory.max,
    );
    document.documentElement.style.setProperty('--agent-history-w', `${pendingW.current}px`);
  }, []);

  const onPointerUp = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    dragging.current = false;
    e.currentTarget.classList.remove('is-dragging');
    document.body.classList.remove('resize-col-active');
    commitLayoutSizes({ agentHistoryW: pendingW.current });
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* already released */
    }
  }, []);

  return { onPointerDown, onPointerMove, onPointerUp };
}
