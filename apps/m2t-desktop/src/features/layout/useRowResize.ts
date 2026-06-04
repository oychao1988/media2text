import { useCallback, useRef, type PointerEvent as ReactPointerEvent } from 'react';
import { clamp, SIZE_LIMITS } from './layoutConstants';
import { useLayoutStore } from './useLayoutStore';

export function useRowResize() {
  const { setAgentH } = useLayoutStore();
  const dragging = useRef(false);
  const startY = useRef(0);
  const startH = useRef(0);

  const onPointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    dragging.current = true;
    startY.current = e.clientY;
    startH.current = parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue('--right-agent-h'),
    );
    e.currentTarget.setPointerCapture(e.pointerId);
    document.body.classList.add('resize-row-active');
    e.currentTarget.classList.add('is-dragging');
  }, []);

  const endDrag = useCallback((el: HTMLDivElement, pointerId: number) => {
    dragging.current = false;
    document.body.classList.remove('resize-row-active');
    el.classList.remove('is-dragging');
    try {
      el.releasePointerCapture(pointerId);
    } catch {
      /* already released */
    }
  }, []);

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!dragging.current) return;
      const dy = e.clientY - startY.current;
      setAgentH(
        clamp(startH.current + dy, SIZE_LIMITS.agent.min, SIZE_LIMITS.agent.max),
      );
    },
    [setAgentH],
  );

  const onPointerUp = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (dragging.current) endDrag(e.currentTarget, e.pointerId);
    },
    [endDrag],
  );

  return { onPointerDown, onPointerMove, onPointerUp };
}
