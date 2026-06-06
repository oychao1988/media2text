import { useCallback, useRef, type PointerEvent as ReactPointerEvent } from 'react';
import {
  applyLayoutSizesTransient,
  clampAgentH,
  readLayoutSizesFromCss,
} from './layoutConstants';
import { commitLayoutSizes } from './useLayoutStore';

function setAppResizing(active: boolean) {
  document.getElementById('app')?.classList.toggle('is-resizing', active);
}

export function useRowResize() {
  const dragging = useRef(false);
  const startY = useRef(0);
  const startH = useRef(0);
  const pendingH = useRef(0);

  const onPointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    dragging.current = true;
    startY.current = e.clientY;
    startH.current = readLayoutSizesFromCss().agentH;
    pendingH.current = clampAgentH(startH.current);
    e.currentTarget.setPointerCapture(e.pointerId);
    document.body.classList.add('resize-row-active');
    setAppResizing(true);
    e.currentTarget.classList.add('is-dragging');
  }, []);

  const endDrag = useCallback((el: HTMLDivElement, pointerId: number) => {
    if (!dragging.current) return;
    dragging.current = false;
    document.body.classList.remove('resize-row-active');
    setAppResizing(false);
    el.classList.remove('is-dragging');
    commitLayoutSizes({ agentH: pendingH.current });
    try {
      el.releasePointerCapture(pointerId);
    } catch {
      /* already released */
    }
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    const dy = e.clientY - startY.current;
    pendingH.current = clampAgentH(startH.current - dy);
    applyLayoutSizesTransient({ agentH: pendingH.current });
  }, []);

  const onPointerUp = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      endDrag(e.currentTarget, e.pointerId);
    },
    [endDrag],
  );

  return { onPointerDown, onPointerMove, onPointerUp };
}
