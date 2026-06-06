import { useCallback, useEffect, useRef } from 'react';

const CHAT_SCROLL_TAIL_PX = 48;

export function useAgentChatScroll(threadKey: string | null, scrollDeps: unknown[]) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);

  useEffect(() => {
    followRef.current = true;
  }, [threadKey]);

  useEffect(() => {
    if (!followRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    const id = requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
    return () => cancelAnimationFrame(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- caller supplies meaningful deps
  }, scrollDeps);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const tail = el.scrollHeight - el.scrollTop - el.clientHeight;
    followRef.current = tail <= CHAT_SCROLL_TAIL_PX;
  }, []);

  return { scrollRef, onScroll };
}
