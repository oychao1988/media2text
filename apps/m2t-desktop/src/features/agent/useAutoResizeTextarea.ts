import { useLayoutEffect, useRef } from 'react';

const DEFAULT_MAX_LINES = 10;

export function useAutoResizeTextarea(value: string, maxLines = DEFAULT_MAX_LINES) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const styles = getComputedStyle(el);
    const lineHeight = parseFloat(styles.lineHeight) || 19;
    const paddingTop = parseFloat(styles.paddingTop) || 0;
    const paddingBottom = parseFloat(styles.paddingBottom) || 0;
    const maxHeight = lineHeight * maxLines + paddingTop + paddingBottom;

    el.style.height = '0px';
    const scrollHeight = el.scrollHeight;
    el.style.height = `${Math.min(scrollHeight, maxHeight)}px`;
    el.style.overflowY = scrollHeight > maxHeight ? 'auto' : 'hidden';
  }, [maxLines, value]);

  return ref;
}
