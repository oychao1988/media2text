import { useCallback, useRef, type PointerEvent as ReactPointerEvent } from 'react';
import { clamp, SIZE_LIMITS } from './layoutConstants';
import { useLayoutStore } from './useLayoutStore';

type Side = 'left' | 'right';

export function useColumnResize() {
  const { leftCollapsed, rightCollapsed, setSidebarW, setRightW } = useLayoutStore();
  const dragging = useRef<Side | null>(null);
  const startX = useRef(0);
  const startW = useRef(0);

  const onLeftPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (leftCollapsed) return;
      dragging.current = 'left';
      startX.current = e.clientX;
      startW.current = parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue('--sidebar-w'),
      );
      e.currentTarget.setPointerCapture(e.pointerId);
      document.body.classList.add('resize-col-active');
      e.currentTarget.classList.add('is-dragging');
    },
    [leftCollapsed],
  );

  const onRightPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (rightCollapsed) return;
      dragging.current = 'right';
      startX.current = e.clientX;
      startW.current = parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue('--right-w'),
      );
      e.currentTarget.setPointerCapture(e.pointerId);
      document.body.classList.add('resize-col-active');
      e.currentTarget.classList.add('is-dragging');
    },
    [rightCollapsed],
  );

  const endDrag = useCallback((el: HTMLDivElement, pointerId: number) => {
    dragging.current = null;
    document.body.classList.remove('resize-col-active');
    el.classList.remove('is-dragging');
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
        setSidebarW(
          clamp(startW.current + dx, SIZE_LIMITS.sidebar.min, SIZE_LIMITS.sidebar.max),
        );
      } else {
        const halfMax = Math.floor(window.innerWidth * 0.5);
        const max = Math.min(halfMax, SIZE_LIMITS.right.max);
        setRightW(clamp(startW.current - dx, SIZE_LIMITS.right.min, max));
      }
    },
    [setSidebarW, setRightW],
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
