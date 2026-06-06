import { useEffect, useMemo, useRef, useState } from 'react';
import {
  filterThreadsByQuery,
  groupThreads,
  THREAD_GROUP_LABELS,
  type ThreadTimeGroup,
} from './threadGroups';
import type { ThreadRow } from './types';

const GROUP_ORDER: ThreadTimeGroup[] = ['today', 'yesterday', 'week', 'month'];

type Props = {
  threads: ThreadRow[];
  activeThreadId: string | null;
  menuOpenThreadId?: string | null;
  editingThreadId?: string | null;
  onSelectThread: (threadId: string) => void;
  onOpenMenu: (threadId: string, anchor: HTMLElement) => void;
  onRenameCommit: (threadId: string, title: string) => void;
  onRenameCancel: () => void;
};

function threadMeta(thread: ThreadRow): string | null {
  if (thread.model && thread.model !== 'auto') return thread.model;
  return null;
}

function ThreadTitleEditor({
  initialTitle,
  onCommit,
  onCancel,
}: {
  initialTitle: string;
  onCommit: (title: string) => void;
  onCancel: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState(initialTitle);
  const committedRef = useRef(false);

  useEffect(() => {
    setDraft(initialTitle);
    committedRef.current = false;
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [initialTitle]);

  const commit = () => {
    if (committedRef.current) return;
    committedRef.current = true;
    const trimmed = draft.trim();
    if (trimmed) onCommit(trimmed);
    else onCancel();
  };

  return (
    <input
      ref={inputRef}
      type="text"
      className="agent-thread-title-input"
      value={draft}
      aria-label="重命名会话"
      onChange={(e) => setDraft(e.target.value)}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          commit();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          onCancel();
        }
      }}
      onBlur={commit}
    />
  );
}

export function AgentHistorySidebar({
  threads,
  activeThreadId,
  menuOpenThreadId = null,
  editingThreadId = null,
  onSelectThread,
  onOpenMenu,
  onRenameCommit,
  onRenameCancel,
}: Props) {
  const [search, setSearch] = useState('');
  const [weekExpanded, setWeekExpanded] = useState(false);

  const grouped = useMemo(() => {
    const filtered = filterThreadsByQuery(groupThreads(threads), search);
    const byGroup = new Map<ThreadTimeGroup, typeof filtered>();
    for (const g of GROUP_ORDER) byGroup.set(g, []);
    for (const t of filtered) {
      byGroup.get(t.group)?.push(t);
    }
    return byGroup;
  }, [search, threads]);

  return (
    <aside className="agent-history" id="agent-history" aria-label="历史会话">
      <input
        className="agent-history-search"
        id="agent-history-search"
        placeholder="搜索 Agent…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <div className="agent-thread-list" id="agent-thread-list" role="list">
        {GROUP_ORDER.map((groupKey) => {
          const items = grouped.get(groupKey) ?? [];
          let visible = items;
          let showMore = false;
          if (groupKey === 'week' && !weekExpanded && items.length > 3) {
            visible = items.slice(0, 3);
            showMore = true;
          }
          if (!visible.length && !showMore) return null;
          return (
            <div key={groupKey} className="agent-thread-group" data-group={groupKey}>
              <div className="agent-thread-group-title">{THREAD_GROUP_LABELS[groupKey]}</div>
              {visible.map((thread) => {
                const meta = threadMeta(thread);
                const selected = thread.id === activeThreadId;
                const menuOpen = thread.id === menuOpenThreadId;
                const editing = thread.id === editingThreadId;
                return (
                  <div
                    key={thread.id}
                    className={[
                      'agent-thread-item',
                      selected ? 'selected' : '',
                      menuOpen ? 'menu-open' : '',
                      editing ? 'is-editing' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    role="listitem"
                    data-thread-id={thread.id}
                  >
                    <span className="agent-thread-icon" aria-hidden="true">
                      ✓
                    </span>
                    <button
                      type="button"
                      className="agent-thread-main"
                      data-thread-id={thread.id}
                      onClick={() => !editing && onSelectThread(thread.id)}
                    >
                      {editing ? (
                        <ThreadTitleEditor
                          initialTitle={thread.title ?? 'Agent'}
                          onCommit={(title) => onRenameCommit(thread.id, title)}
                          onCancel={onRenameCancel}
                        />
                      ) : (
                        <>
                          <span className="agent-thread-title">{thread.title ?? 'Agent'}</span>
                          {meta ? <span className="agent-thread-meta">{meta}</span> : null}
                        </>
                      )}
                    </button>
                    {!editing ? (
                      <button
                        type="button"
                        className="agent-thread-menu-btn"
                        aria-label="更多操作"
                        title="更多"
                        data-thread-id={thread.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          onOpenMenu(thread.id, e.currentTarget);
                        }}
                      >
                        ⋯
                      </button>
                    ) : null}
                  </div>
                );
              })}
              {showMore ? (
                <button
                  type="button"
                  className="agent-thread-more"
                  data-expand-week=""
                  onClick={() => setWeekExpanded(true)}
                >
                  More
                </button>
              ) : null}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
