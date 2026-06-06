import { useCallback, useMemo, useState } from 'react';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { showToast, showToastWithAction } from '../../lib/toast';
import { useCreators } from '../creators/CreatorsContext';
import { positionAgentContextMenu } from './contextMenuPosition';
import { AgentHistorySidebar } from './AgentHistorySidebar';
import { AgentTabsBar } from './AgentTabsBar';
import { AgentThreadContextMenu } from './AgentThreadContextMenu';
import { shouldNotifyCreatorMismatch, isComposerBlocked } from './agentThreadSelect';
import { AgentComposer } from './AgentComposer';
import { ToolResultCard } from './ToolResultCard';
import { ChatMessageUser } from './ChatMessageUser';
import { ChatMessageAgent } from './ChatMessageAgent';
import { resolveAgentProfile } from './agentProfile';
import { useAgentHistoryResize } from './useAgentHistoryResize';
import { activateAgentTab, closeAgentTab, pushAgentTab } from './useAgentTabs';
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
  threadCreatorId,
}: {
  agent: ReturnType<typeof useM2tAgent>;
  threadCreatorId: string | null;
}) {
  const { creators } = useCreators();
  const agentProfile = useMemo(
    () => resolveAgentProfile(threadCreatorId, creators),
    [threadCreatorId, creators],
  );

  return (
    <>
      {agent.messages.map((msg) => {
        if (msg.role === 'user') {
          return (
            <ChatMessageUser key={msg.id} text={msg.text} createdAt={msg.createdAt} />
          );
        }
        if (msg.role === 'tool') {
          return (
            <div key={msg.id} className="chat-msg-tool">
              <ToolResultCard result={msg.result.payload} />
            </div>
          );
        }
        return (
          <ChatMessageAgent
            key={msg.id}
            profile={agentProfile}
            text={msg.text}
            createdAt={msg.createdAt}
            thinkingText={msg.thinkingText}
            durationMs={msg.durationMs}
          />
        );
      })}
      {agent.activeTurn ? (
        <ChatMessageAgent
          profile={agentProfile}
          text={agent.activeTurn.assistantText}
          activePhaseLabel={agent.activeTurn.phaseLabel}
        />
      ) : null}
      {agent.status === 'reconnecting' ? (
        <p className="muted agent-status-hint">Agent 流重连中…</p>
      ) : null}
    </>
  );
}

export function AgentPanel
export function AgentPanel({ creatorId, sessionContext, playbackMode = false }: AgentPanelProps) {
  const { setSelectedId } = useCreators();
  const { threads, createThread, createGlobalThread, renameThread, deleteThread, historyFilter, setHistoryFilter } =
    useAgentThreads(creatorId);
  const [tabIds, setTabIds] = useState<string[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [historyCollapsed, setHistoryCollapsed] = useState(readHistoryCollapsed);
  const [contextMenu, setContextMenu] = useState<{
    threadId: string;
    x: number;
    y: number;
  } | null>(null);
  const [editingThreadId, setEditingThreadId] = useState<string | null>(null);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const historyResize = useAgentHistoryResize();

  const activeThread = useMemo(
    () => threads.find((t) => t.id === activeThreadId) ?? null,
    [activeThreadId, threads],
  );
  const composerBlocked = isComposerBlocked(activeThread?.creator_id, creatorId);

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
    (threadId: string, opts?: { silent?: boolean; reorder?: boolean }) => {
      const thread = threads.find((t) => t.id === threadId);
      if (!thread) return;
      setTabIds((prev) => activateAgentTab(prev, threadId, { reorder: opts?.reorder }));
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

  const handleNewGlobalThread = useCallback(async () => {
    try {
      const thread = await createGlobalThread();
      if (!thread) return;
      setTabIds((prev) => pushAgentTab(prev, thread.id));
      setActiveThreadId(thread.id);
      showToast('已新建全局 Agent 会话', 'success');
    } catch {
      showToast('新建全局会话失败', 'error');
    }
  }, [createGlobalThread]);

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

  const handleRename = useCallback(() => {
    if (!contextMenu) return;
    setEditingThreadId(contextMenu.threadId);
    setContextMenu(null);
  }, [contextMenu]);

  const handleRenameCommit = useCallback(
    async (threadId: string, title: string) => {
      setEditingThreadId(null);
      try {
        await renameThread(threadId, title);
        showToast('已重命名', 'success');
      } catch {
        showToast('重命名失败', 'error');
      }
    },
    [renameThread],
  );

  const handleRenameCancel = useCallback(() => {
    setEditingThreadId(null);
  }, []);

  const handleDelete = useCallback(() => {
    if (!contextMenu) return;
    setDeleteTargetId(contextMenu.threadId);
    setContextMenu(null);
  }, [contextMenu]);

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTargetId) return;
    const id = deleteTargetId;
    setDeleteTargetId(null);
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
  }, [deleteTargetId, deleteThread]);

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
        onSelectTab={(id) => activateThread(id, { reorder: false })}
        onCloseTab={handleCloseTab}
        onNewThread={() => void handleNewThread()}
        onToggleHistory={handleToggleHistory}
      />
      <div className="agent-body">
        <div className="agent-main">
          <div className="chat-scroll" id="chat-scroll" aria-live="polite">
            <div id="chat-live" style={playbackMode ? { display: 'none' } : undefined}>
              {!playbackMode ? <AgentChatMessages agent={agent} threadCreatorId={activeThread?.creator_id ?? null} /> : null}
            </div>
            <div id="chat-playback" style={playbackMode ? undefined : { display: 'none' }}>
              {playbackMode ? <AgentChatMessages agent={agent} threadCreatorId={activeThread?.creator_id ?? null} /> : null}
            </div>
            {!activeThreadId ? (
              <p className="hint">点击 + 新建 Agent，或从历史栏选择会话</p>
            ) : null}
            {composerBlocked ? (
              <div
                className="agent-mismatch-banner"
                id="agent-mismatch-banner"
                role="alert"
              >
                <span>该会话属于其他博主，请先切换到对应博主后再发送。</span>
                {activeThread?.creator_id ? (
                  <button
                    type="button"
                    className="agent-mismatch-cta"
                    onClick={() => setSelectedId(activeThread.creator_id)}
                  >
                    切换到该博主
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
          <AgentComposer
            ready={agent.ready && !composerBlocked}
            blocked={composerBlocked}
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
              historyFilter={historyFilter}
              onHistoryFilterChange={setHistoryFilter}
              onNewGlobalThread={() => void handleNewGlobalThread()}
              menuOpenThreadId={contextMenu?.threadId ?? null}
              editingThreadId={editingThreadId}
              onSelectThread={(id) => activateThread(id)}
              onOpenMenu={(threadId, anchor) => {
                const rect = anchor.getBoundingClientRect();
                const { x, y } = positionAgentContextMenu(rect);
                setContextMenu({ threadId, x, y });
              }}
              onRenameCommit={(id, title) => void handleRenameCommit(id, title)}
              onRenameCancel={handleRenameCancel}
            />
          </>
        ) : null}
      </div>
      {contextMenu ? (
        <AgentThreadContextMenu
          threadId={contextMenu.threadId}
          x={contextMenu.x}
          y={contextMenu.y}
          onRename={handleRename}
          onDelete={handleDelete}
          onClose={() => setContextMenu(null)}
        />
      ) : null}
      <ConfirmDialog
        open={deleteTargetId != null}
        title="删除 Agent 会话"
        message="确定删除该 Agent 会话？此操作不可撤销。"
        confirmLabel="删除"
        danger
        onConfirm={() => void handleDeleteConfirm()}
        onCancel={() => setDeleteTargetId(null)}
      />
    </section>
  );
}
