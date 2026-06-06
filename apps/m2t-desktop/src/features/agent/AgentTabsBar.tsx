import type { ThreadRow } from './types';

type Props = {
  tabIds: string[];
  threads: ThreadRow[];
  activeThreadId: string | null;
  historyCollapsed: boolean;
  onSelectTab: (threadId: string) => void;
  onCloseTab: (threadId: string) => void;
  onNewThread: () => void;
  onToggleHistory: () => void;
};

export function AgentTabsBar({
  tabIds,
  threads,
  activeThreadId,
  historyCollapsed,
  onSelectTab,
  onCloseTab,
  onNewThread,
  onToggleHistory,
}: Props) {
  const threadById = new Map(threads.map((t) => [t.id, t]));

  return (
    <div className="agent-tabs-bar" id="agent-tabs-bar">
      <div className="agent-tabs-scroll" id="agent-tabs-row" role="tablist">
        {tabIds.map((id) => {
          const thread = threadById.get(id);
          if (!thread) return null;
          const active = id === activeThreadId;
          return (
            <div
              key={id}
              className={`agent-tab-wrap${active ? ' active' : ''}`}
              data-thread-id={id}
            >
              <button
                type="button"
                className="agent-tab"
                role="tab"
                aria-selected={active}
                title={thread.title ?? 'Agent'}
                onClick={() => onSelectTab(id)}
              >
                {thread.title ?? 'Agent'}
              </button>
              <button
                type="button"
                className="agent-tab-close"
                aria-label="关闭页签"
                onClick={(e) => {
                  e.stopPropagation();
                  onCloseTab(id);
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
          className="icon-btn agent-tabs-action"
          id="btn-agent-new"
          title="新建 Agent"
          aria-label="新建 Agent"
          onClick={onNewThread}
        >
          +
        </button>
        <button
          type="button"
          className="icon-btn agent-tabs-action"
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
