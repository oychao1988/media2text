import { useEffect, useMemo, useRef, useState } from 'react';
import { AgentAvatar, type AgentCreatorRef } from './AgentAvatar';
import {
  filterThreadsByQuery,
  groupThreadsByAgent,
  type AgentThreadGroup,
} from './agentGroups';
import { readAgentGroupCollapsed, writeAgentGroupCollapsed } from './agentGroupCollapse';
import type { ThreadRow } from './types';

type Props = {
  threads: ThreadRow[];
  creators: AgentCreatorRef[];
  activeThreadId: string | null;
  menuOpenThreadId?: string | null;
  editingThreadId?: string | null;
  onSelectThread: (threadId: string) => void;
  onOpenMenu: (threadId: string, anchor: HTMLElement) => void;
  onRenameCommit: (threadId: string, title: string) => void;
  onRenameCancel: () => void;
  onBatchDeleteRequest: (agentId: string, threadIds: string[]) => void;
};

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

function AgentGroupSection({
  group,
  collapsed,
  onToggleCollapse,
  activeThreadId,
  menuOpenThreadId,
  editingThreadId,
  onSelectThread,
  onOpenMenu,
  onRenameCommit,
  onRenameCancel,
  onBatchDeleteRequest,
  creators,
}: {
  group: AgentThreadGroup;
  creators: AgentCreatorRef[];
  collapsed: boolean;
  onToggleCollapse: () => void;
  activeThreadId: string | null;
  menuOpenThreadId: string | null;
  editingThreadId: string | null;
  onSelectThread: (threadId: string) => void;
  onOpenMenu: (threadId: string, anchor: HTMLElement) => void;
  onRenameCommit: (threadId: string, title: string) => void;
  onRenameCancel: () => void;
  onBatchDeleteRequest: (agentId: string, threadIds: string[]) => void;
}) {
  const { agentId, profile, threads } = group;

  return (
    <div
      className={`agent-thread-group${collapsed ? ' collapsed' : ''}`}
      data-agent-id={agentId}
    >
      <div className="agent-thread-group-head">
        <button
          type="button"
          className="agent-thread-group-toggle"
          aria-expanded={!collapsed}
          onClick={onToggleCollapse}
        >
          <span className="agent-thread-group-chevron" aria-hidden="true">
            ▾
          </span>
          <AgentAvatar profile={profile} creators={creators} size="group" />
          <span className="agent-thread-group-name">{profile.name}</span>
        </button>
        <div className="agent-thread-group-actions">
          <button
            type="button"
            className="agent-thread-group-action"
            title="删除该 Agent 下全部会话"
            aria-label={`删除 ${profile.name} 下全部会话`}
            onClick={() => onBatchDeleteRequest(agentId, threads.map((t) => t.id))}
          >
            ⌫
          </button>
        </div>
      </div>
      {!collapsed ? (
        <div className="agent-thread-group-sessions">
          {threads.map((thread) => {
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
                    <span className="agent-thread-title">{thread.title ?? 'Agent'}</span>
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
        </div>
      ) : null}
    </div>
  );
}

export function AgentHistorySidebar({
  threads,
  creators,
  activeThreadId,
  menuOpenThreadId = null,
  editingThreadId = null,
  onSelectThread,
  onOpenMenu,
  onRenameCommit,
  onRenameCancel,
  onBatchDeleteRequest,
}: Props) {
  const [search, setSearch] = useState('');
  const [collapsedMap, setCollapsedMap] = useState(readAgentGroupCollapsed);

  const filtered = useMemo(
    () => filterThreadsByQuery(threads, search),
    [search, threads],
  );

  const groups = useMemo(
    () => groupThreadsByAgent(filtered, creators),
    [filtered, creators],
  );

  const toggleGroup = (agentId: string) => {
    setCollapsedMap((prev) => {
      const next = { ...prev, [agentId]: !prev[agentId] };
      writeAgentGroupCollapsed(next);
      return next;
    });
  };

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
        {!groups.length ? (
          <p className="agent-history-empty muted">暂无会话</p>
        ) : (
          groups.map((group) => (
            <AgentGroupSection
              key={group.agentId}
              group={group}
              creators={creators}
              collapsed={Boolean(collapsedMap[group.agentId])}
              onToggleCollapse={() => toggleGroup(group.agentId)}
              activeThreadId={activeThreadId}
              menuOpenThreadId={menuOpenThreadId}
              editingThreadId={editingThreadId}
              onSelectThread={onSelectThread}
              onOpenMenu={onOpenMenu}
              onRenameCommit={onRenameCommit}
              onRenameCancel={onRenameCancel}
              onBatchDeleteRequest={onBatchDeleteRequest}
            />
          ))
        )}
      </div>
    </aside>
  );
}
