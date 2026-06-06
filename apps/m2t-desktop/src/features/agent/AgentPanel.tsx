import { useCallback, useMemo, useState } from 'react';
import { showToast, showToastWithAction } from '../../lib/toast';
import { useCreators } from '../creators/CreatorsContext';
import { AgentHistorySidebar } from './AgentHistorySidebar';
import { AgentTabsBar } from './AgentTabsBar';
import { AgentThreadContextMenu } from './AgentThreadContextMenu';
import { shouldNotifyCreatorMismatch } from './agentThreadSelect';
import { ChatMarkdown } from './ChatMarkdown';
import { AgentComposer } from './AgentComposer';
import { ToolResultCard } from './ToolResultCard';
import { useAgentHistoryResize } from './useAgentHistoryResize';
import { closeAgentTab, pushAgentTab } from './useAgentTabs';
import { useAgentThreads } from './useAgentThreads';
import { useM2tAgent, type SessionContext } from './useM2tAgent';

const AGENT_HISTORY_KEY = 'm2t-agent-history-collapsed';

type AgentPanelProps = {
  creatorId: string | null;
  sessionContext: SessionContext;
  playbackMode?: boolean;
};

function readHistoryCollapsed(): boolean {
  try {
    return localStorage.getItem(AGENT_HISTORY_KEY) === '1';
  } catch {
    return false;
  }
}

function AgentChatMessages({
  agent,
}: {
  agent: ReturnType<typeof useM2tAgent>;
}) {
  return (
    <>
      {agent.messages.map((msg) => {
        if (msg.role === 'user') {
          return (
            <div key={msg.id} className="msg msg-user">
              <ChatMarkdown text={msg.text} />
            </div>
          );
        }
        if (msg.role === 'tool') {
          return (
            <div key={msg.id} className="msg msg-assistant">
              <ToolResultCard result={msg.result.payload} />
            </div>
          );
        }
        return (
          <div key={msg.id} className="msg msg-assistant">
            {msg.thinkingText ? (
              <div className="thinking">
                <ChatMarkdown text={msg.thinkingText} />
              </div>
            ) : null}
            <ChatMarkdown text={msg.text} />
          </div>
        );
      })}
      {agent.activeTurn ? (
        <div className="msg msg-assistant">
          <p className="muted agent-phase">{agent.activeTurn.phaseLabel}</p>
          {agent.activeTurn.thinkingText ? (
            <div className="thinking">
              <ChatMarkdown text={agent.activeTurn.thinkingText} />
            </div>
          ) : null}
          {agent.activeTurn.assistantText ? (
            <ChatMarkdown text={agent.activeTurn.assistantText} />
          ) : null}
        </div>
      ) : null}
      {agent.status === 'crashed' ? (
        <p className="muted agent-status-hint">Agent 已退出，正在尝试恢复…</p>
      ) : null}
    </>
  );
}

export function AgentPanel({ creatorId, sessionContext, playbackMode = false }: AgentPanelProps) {
  const { setSelectedId } = useCreators();
  const { threads, createThread, renameThread, deleteThread } = useAgentThreads();
  const [tabIds, setTabIds] = useState<string[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [historyCollapsed, setHistoryCollapsed] = useState(readHistoryCollapsed);
  const [contextMenu, setContextMenu] = useState<{
    threadId: string;
    x: number;
    y: number;
  } | null>(null);
  const historyResize = useAgentHistoryResize();

  const agent = useM2tAgent({
    threadId: activeThreadId,
    creatorId,
    sessionContext,
  });

  const modelOptions = useMemo(() => {
    const set = new Set<string>();
    for (const p of agent.providers) {
      for (const m of p.models ?? []) set.add(m);
    }
    return [...set];
  }, [agent.providers]);

  const activateThread = useCallback(
    (threadId: string, opts?: { silent?: boolean }) => {
      const thread = threads.find((t) => t.id === threadId);
      if (!thread) return;
      setTabIds((prev) => pushAgentTab(prev, threadId));
      setActiveThreadId(threadId);
      if (
        !opts?.silent &&
        shouldNotifyCreatorMismatch(thread.creator_id, creatorId)
      ) {
        showToastWithAction(
          '该会话属于其他博主',
          'info',
          8000,
          {
            label: '切换到该博主',
            onAction: () => setSelectedId(thread.creator_id),
          },
        );
      } else if (!opts?.silent) {
        showToast(`已切换：${thread.title ?? 'Agent'}`, 'info');
      }
    },
    [creatorId, setSelectedId, threads],
  );

  const handleNewThread = useCallback(async () => {
    if (!creatorId) {
      showToast('请先选择博主', 'info');
      return;
    }
    try {
      const thread = await createThread(creatorId, sessionContext.sessionId);
      if (!thread) return;
      setTabIds((prev) => pushAgentTab(prev, thread.id));
      setActiveThreadId(thread.id);
      showToast('已新建 Agent 会话', 'success');
    } catch {
      showToast('新建会话失败', 'error');
    }
  }, [createThread, creatorId, sessionContext.sessionId]);

  const handleCloseTab = useCallback(
    (threadId: string) => {
      setTabIds((prev) => {
        const { tabIds: next, activeId } = closeAgentTab(prev, threadId, activeThreadId);
        setActiveThreadId(activeId);
        return next;
      });
      showToast('已关闭页签', 'info');
    },
    [activeThreadId],
  );

  const handleToggleHistory = useCallback(() => {
    setHistoryCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(AGENT_HISTORY_KEY, next ? '1' : '0');
      } catch {
        /* ignore */
      }
      showToast(next ? '已隐藏历史会话栏' : '已显示历史会话栏', 'info');
      return next;
    });
  }, []);

  const handleRename = useCallback(async () => {
    if (!contextMenu) return;
    const title = window.prompt('重命名会话', threads.find((t) => t.id === contextMenu.threadId)?.title ?? '');
    setContextMenu(null);
    if (!title?.trim()) return;
    try {
      await renameThread(contextMenu.threadId, title.trim());
      showToast('已重命名', 'success');
    } catch {
      showToast('重命名失败', 'error');
    }
  }, [contextMenu, renameThread, threads]);

  const handleDelete = useCallback(async () => {
    if (!contextMenu) return;
    const id = contextMenu.threadId;
    setContextMenu(null);
    if (!window.confirm('确定删除该 Agent 会话？此操作不可撤销。')) return;
    try {
      await deleteThread(id);
      setTabIds((prev) => {
        const next = prev.filter((x) => x !== id);
        setActiveThreadId((active) => (active === id ? (next[0] ?? null) : active));
        return next;
      });
      showToast('已删除会话', 'success');
    } catch {
      showToast('删除失败', 'error');
    }
  }, [contextMenu, deleteThread]);

  const paneClass = [
    'agent-pane',
    historyCollapsed ? 'agent-history-collapsed' : '',
    agent.fatalError && agent.status === 'error' ? 'agent-pane--error' : '',
  ]
    .filter(Boolean)
    .join(' ');

  if (agent.fatalError && agent.status === 'error') {
    return (
      <section className={paneClass} aria-label="Agent">
        <div className="chat-scroll" id="chat-scroll" role="alert">
          <p className="agent-error-title">Agent 不可用</p>
          <p className="muted">{agent.fatalError}</p>
          <p className="muted agent-error-hint">监控与转写不受影响，请检查 LLM 配置后重试。</p>
        </div>
      </section>
    );
  }

  return (
    <section className={paneClass} aria-label="Agent" id="agent-pane">
      <AgentTabsBar
        tabIds={tabIds}
        threads={threads}
        activeThreadId={activeThreadId}
        historyCollapsed={historyCollapsed}
        onSelectTab={(id) => activateThread(id)}
        onCloseTab={handleCloseTab}
        onNewThread={() => void handleNewThread()}
        onToggleHistory={handleToggleHistory}
      />
      <div className="agent-body">
        <div className="agent-main">
          <div className="chat-scroll" id="chat-scroll" aria-live="polite">
            <div id="chat-live" style={playbackMode ? { display: 'none' } : undefined}>
              {!playbackMode ? <AgentChatMessages agent={agent} /> : null}
            </div>
            <div id="chat-playback" style={playbackMode ? undefined : { display: 'none' }}>
              {playbackMode ? <AgentChatMessages agent={agent} /> : null}
            </div>
            {!activeThreadId ? (
              <p className="hint">点击 + 新建 Agent，或从历史栏选择会话</p>
            ) : null}
          </div>
          <AgentComposer
            ready={agent.ready}
            model={agent.threadModel}
            providerModels={modelOptions}
            onModelChange={(m) => void agent.patchThreadModel(m)}
            onSend={(t) => void agent.sendMessage(t)}
          />
        </div>
        {!historyCollapsed ? (
          <>
            <div
              className="agent-col-resize"
              id="resize-agent-history"
              role="separator"
              aria-orientation="vertical"
              aria-label="调整历史栏宽度"
              tabIndex={0}
              onPointerDown={historyResize.onPointerDown}
              onPointerMove={historyResize.onPointerMove}
              onPointerUp={historyResize.onPointerUp}
            />
            <AgentHistorySidebar
              threads={threads}
              activeThreadId={activeThreadId}
              onSelectThread={(id) => activateThread(id)}
              onOpenMenu={(threadId, anchor) => {
                const rect = anchor.getBoundingClientRect();
                setContextMenu({ threadId, x: rect.left, y: rect.bottom + 4 });
              }}
            />
          </>
        ) : null}
      </div>
      {contextMenu ? (
        <AgentThreadContextMenu
          threadId={contextMenu.threadId}
          x={contextMenu.x}
          y={contextMenu.y}
          onRename={() => void handleRename()}
          onDelete={() => void handleDelete()}
          onClose={() => setContextMenu(null)}
        />
      ) : null}
    </section>
  );
}
