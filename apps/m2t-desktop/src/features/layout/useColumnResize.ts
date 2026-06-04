import { useCallback, useRef, type PointerEvent as ReactPointerEvent } from 'react';
import {
  applyLayoutSizesTransient,
  clamp,
  maxRightWForViewport,
  maxSidebarWForViewport,
  SIZE_LIMITS,
} from './layoutConstants';
import { commitLayoutSizes, useLayoutStore } from './useLayoutStore';

type Side = 'left' | 'right';

function setAppResizing(active: boolean) {
  document.getElementById('app')?.classList.toggle('is-resizing', active);
}

export function useColumnResize() {
  const { leftCollapsed, rightCollapsed } = useLayoutStore();
  const dragging = useRef<Side | null>(null);
  const startX = useRef(0);
  const startSidebarW = useRef(0);
  const startRightW = useRef(0);
  const pendingSidebarW = useRef(0);
  const pendingRightW = useRef(0);

  const beginDrag = useCallback(
    (side: Side, e: ReactPointerEvent<HTMLDivElement>) => {
      dragging.current = side;
      startX.current = e.clientX;
      const cs = getComputedStyle(document.documentElement);
      startSidebarW.current = parseFloat(cs.getPropertyValue('--sidebar-w'));
      startRightW.current = parseFloat(cs.getPropertyValue('--right-w'));
      pendingSidebarW.current = startSidebarW.current;
      pendingRightW.current = startRightW.current;
      e.currentTarget.setPointerCapture(e.pointerId);
      document.body.classList.add('resize-col-active');
      setAppResizing(true);
      e.currentTarget.classList.add('is-dragging');
    },
    [],
  );

  const onLeftPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (leftCollapsed) return;
      beginDrag('left', e);
    },
    [beginDrag, leftCollapsed],
  );

  const onRightPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (rightCollapsed) return;
      beginDrag('right', e);
    },
    [beginDrag, rightCollapsed],
  );

  const endDrag = useCallback((el: HTMLDivElement, pointerId: number) => {
    const side = dragging.current;
    if (!side) return;
    dragging.current = null;
    document.body.classList.remove('resize-col-active');
    setAppResizing(false);
    el.classList.remove('is-dragging');
    if (side === 'left') {
      commitLayoutSizes({ sidebarW: pendingSidebarW.current });
    } else {
      commitLayoutSizes({ rightW: pendingRightW.current });
    }
    try {
      el.releasePointerCapture(pointerId);
    } catch {
      /* already released */
    }
  }, []);

  const onPointerMove = useCallback(
    (side: Side) => (e: React.PointerEvent<HTMLDivElement>) => {
      if (dragging.current !== side) return;
      const dx = e.clientX - startX.current;
      if (side === 'left') {
        pendingSidebarW.current = clamp(
          startSidebarW.current + dx,
          SIZE_LIMITS.sidebar.min,
          maxSidebarWForViewport(startRightW.current),
        );
        applyLayoutSizesTransient({ sidebarW: pendingSidebarW.current });
      } else {
        pendingRightW.current = clamp(
          startRightW.current - dx,
          SIZE_LIMITS.right.min,
          maxRightWForViewport(startSidebarW.current),
        );
        applyLayoutSizesTransient({ rightW: pendingRightW.current });
      }
    },
    [],
  );

  const onPointerUp = useCallback(
    (side: Side) => (e: React.PointerEvent<HTMLDivElement>) => {
      if (dragging.current === side) endDrag(e.currentTarget, e.pointerId);
    },
    [endDrag],
  );

  return {
    onLeftPointerDown,
    onRightPointerDown,
    onLeftPointerMove: onPointerMove('left'),
    onRightPointerMove: onPointerMove('right'),
    onLeftPointerUp: onPointerUp('left'),
    onRightPointerUp: onPointerUp('right'),
  };
}
