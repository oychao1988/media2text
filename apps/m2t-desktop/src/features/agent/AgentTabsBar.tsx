import { useLayoutEffect, useRef } from 'react';
import { AgentAvatar } from './AgentAvatar';
import { resolveAgentProfile } from './agentProfile';
import {
  tabEntryKey,
  type AgentTabEntry,
} from './useAgentTabs';
import type { ThreadRow } from './types';

type Props = {
  tabEntries: AgentTabEntry[];
  threads: ThreadRow[];
  creators: Array<{
    id: string;
    display_name: string | null;
    avatar_url?: string | null;
    profile_synced_at?: string | null;
  }>;
  activeTabKey: string | null;
  historyCollapsed: boolean;
  onSelectTab: (key: string) => void;
  onCloseTab: (key: string) => void;
  onNewDraft: () => void;
  onToggleHistory: () => void;
};

function tabLabel(entry: AgentTabEntry, thread: ThreadRow | undefined): string {
  if (entry.kind === 'thread') {
    return thread?.title ?? 'Agent';
  }
  return '新对话';
}

export function AgentTabsBar({
  tabEntries,
  threads,
  creators,
  activeTabKey,
  historyCollapsed,
  onSelectTab,
  onCloseTab,
  onNewDraft,
  onToggleHistory,
}: Props) {
  const threadById = new Map(threads.map((t) => [t.id, t]));
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollLeftRef = useRef(0);

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollLeft = scrollLeftRef.current;
  }, [activeTabKey, tabEntries.length]);

  const handleSelectTab = (key: string) => {
    scrollLeftRef.current = scrollRef.current?.scrollLeft ?? 0;
    onSelectTab(key);
  };

  return (
    <div className="agent-tabs-bar" id="agent-tabs-bar">
      <div
        className="agent-tabs-scroll"
        id="agent-tabs-row"
        role="tablist"
        ref={scrollRef}
      >
        {tabEntries.map((entry) => {
          const key = tabEntryKey(entry);
          const thread = entry.kind === 'thread' ? threadById.get(entry.threadId) : undefined;
          const active = key === activeTabKey;
          const agentId =
            entry.kind === 'draft'
              ? entry.agentId
              : thread?.creator_id ?? 'global';
          const profile = resolveAgentProfile(
            agentId === 'global' ? null : agentId,
            creators,
          );
          const label = tabLabel(entry, thread);
          return (
            <div
              key={key}
              className={`agent-tab-wrap${active ? ' active' : ''}`}
              data-tab-key={key}
            >
              <button
                type="button"
                className="agent-tab"
                role="tab"
                aria-selected={active}
                title={label}
                onClick={() => handleSelectTab(key)}
              >
                <AgentAvatar profile={profile} creators={creators} size="tab" />
                <span className="agent-tab-label">{label}</span>
              </button>
              <button
                type="button"
                className="agent-tab-close"
                aria-label="关闭页签"
                onClick={(e) => {
                  e.stopPropagation();
                  onCloseTab(key);
                }}
              >
                ×
              </button>
            </div>
          );
        })}
      </div>
      <div className="agent-tabs-actions">
        <button
          type="button"
          className="agent-header-icon-btn"
          id="btn-agent-new"
          title="新建 Agent"
          aria-label="新建 Agent"
          onClick={onNewDraft}
        >
          +
        </button>
        <button
          type="button"
          className="agent-header-icon-btn"
          id="btn-agent-history-toggle"
          title={historyCollapsed ? '显示历史会话' : '隐藏历史会话'}
          aria-label={historyCollapsed ? '显示历史会话' : '隐藏历史会话'}
          aria-pressed={!historyCollapsed}
          onClick={onToggleHistory}
        >
          ☰
        </button>
      </div>
    </div>
  );
}
