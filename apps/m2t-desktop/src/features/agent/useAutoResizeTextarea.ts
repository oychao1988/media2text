import { useCallback, useLayoutEffect, useRef } from 'react';

const DEFAULT_MAX_LINES = 10;

function supportsFieldSizing(): boolean {
  if (typeof CSS === 'undefined' || !CSS.supports) return false;
  return CSS.supports('field-sizing', 'content');
}

export function useAutoResizeTextarea(value: string, maxLines = DEFAULT_MAX_LINES) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const fieldSizingRef = useRef<boolean | null>(null);

  const syncHeight = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    if (fieldSizingRef.current === null) {
      fieldSizingRef.current = supportsFieldSizing();
    }
    if (fieldSizingRef.current) {
      el.style.removeProperty('height');
      el.style.removeProperty('overflow-y');
      return;
    }

    const styles = getComputedStyle(el);
    const lineHeight = parseFloat(styles.lineHeight) || 19;
    const paddingTop = parseFloat(styles.paddingTop) || 0;
    const paddingBottom = parseFloat(styles.paddingBottom) || 0;
    const maxHeight = lineHeight * maxLines + paddingTop + paddingBottom;

    if (!value.trim()) {
      el.style.removeProperty('height');
      el.style.overflowY = 'hidden';
      return;
    }

    el.style.height = '0px';
    const scrollHeight = el.scrollHeight;
    el.style.height = `${Math.min(scrollHeight, maxHeight)}px`;
    el.style.overflowY = scrollHeight > maxHeight ? 'auto' : 'hidden';
  }, [maxLines, value]);

  useLayoutEffect(() => {
    syncHeight();
  }, [syncHeight]);

  const onInput = useCallback(() => {
    syncHeight();
  }, [syncHeight]);

  return { ref, onInput };
}
