import { useEffect, useRef } from 'react';
import type { MentionDocumentRow } from './mentionDocuments';

type AgentMentionPopoverProps = {
  open: boolean;
  rows: MentionDocumentRow[];
  loading: boolean;
  activeIndex: number;
  onSelect: (row: MentionDocumentRow) => void;
  onActiveIndexChange: (index: number) => void;
};

export function AgentMentionPopover({
  open,
  rows,
  loading,
  activeIndex,
  onSelect,
  onActiveIndexChange,
}: AgentMentionPopoverProps) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const el = listRef.current?.querySelector<HTMLElement>(`[data-mention-idx="${activeIndex}"]`);
    el?.scrollIntoView?.({ block: 'nearest' });
  }, [activeIndex, open]);

  if (!open) return null;

  return (
    <div className="agent-mention-popover" role="listbox" aria-label="引用文档">
      {loading && rows.length === 0 ? (
        <div className="agent-mention-empty">加载文档…</div>
      ) : null}
      {!loading && rows.length === 0 ? (
        <div className="agent-mention-empty">无匹配文档</div>
      ) : null}
      <div className="agent-mention-list" ref={listRef}>
        {rows.map((row, idx) => (
          <button
            key={row.rowKey}
            type="button"
            role="option"
            aria-selected={idx === activeIndex}
            data-mention-idx={idx}
            className={`agent-mention-item${idx === activeIndex ? ' agent-mention-item--active' : ''}`}
            onMouseEnter={() => onActiveIndexChange(idx)}
            onMouseDown={(e) => {
              e.preventDefault();
              onSelect(row);
            }}
          >
            {row.label}
          </button>
        ))}
      </div>
    </div>
  );
}
