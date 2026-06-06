import { useCallback, useMemo, useState } from 'react';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { showToast, showToastWithAction } from '../../lib/toast';
import { useCreators } from '../creators/CreatorsContext';
import { positionAgentContextMenu } from './contextMenuPosition';
import { AgentChatEmpty, composerPlaceholderForAgent } from './AgentChatEmpty';
import { AgentHistorySidebar } from './AgentHistorySidebar';
import { AgentTabsBar } from './AgentTabsBar';
import { AgentThreadContextMenu } from './AgentThreadContextMenu';
import { shouldNotifyCreatorMismatch, isComposerBlocked } from './agentThreadSelect';
import { resolveAgentProfile } from './agentProfile';
import { ChatMessageAgent } from './ChatMessageAgent';
import { ChatMessageUser } from './ChatMessageUser';
import { AgentComposer } from './AgentComposer';
import { ToolResultCard } from './ToolResultCard';
import { useAgentHistoryResize } from './useAgentHistoryResize';
import {
  activateAgentTabEntry,
  closeAgentTabEntry,
  createDraftTab,
  promoteDraftTab,
  pushAgentTabEntry,
  removeThreadFromTabs,
  tabEntryKey,
  type AgentTabEntry,
} from './useAgentTabs';
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

export function AgentPanel({ creatorId, sessionContext, playbackMode = false }: AgentPanelProps) {
  const { creators, setSelectedId } = useCreators();
  const { threads, createThread, createGlobalThread, renameThread, deleteThread } =
    useAgentThreads(creatorId);
  const [tabEntries, setTabEntries] = useState<AgentTabEntry[]>([]);
  const [activeTabKey, setActiveTabKey] = useState<string | null>(null);
  const [historyCollapsed, setHistoryCollapsed] = useState(readHistoryCollapsed);
  const [contextMenu, setContextMenu] = useState<{
    threadId: string;
    x: number;
    y: number;
  } | null>(null);
  const [editingThreadId, setEditingThreadId] = useState<string | null>(null);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [batchDeleteTarget, setBatchDeleteTarget] = useState<{
    agentId: string;
    threadIds: string[];
  } | null>(null);
  const historyResize = useAgentHistoryResize();

  const activeEntry = useMemo(
    () => tabEntries.find((e) => tabEntryKey(e) === activeTabKey) ?? null,
    [activeTabKey, tabEntries],
  );

  const activeThreadId =
    activeEntry?.kind === 'thread' ? activeEntry.threadId : null;

  const isDraftActive = activeEntry?.kind === 'draft';
  const draftAgentId = activeEntry?.kind === 'draft' ? activeEntry.agentId : 'global';

  const activeThread = useMemo(
    () => threads.find((t) => t.id === activeThreadId) ?? null,
    [activeThreadId, threads],
  );

  const composerBlocked = isDraftActive
    ? false
    : isComposerBlocked(activeThread?.creator_id, creatorId);

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

  const composerReady = agent.ready && !composerBlocked;
  const composerPlaceholder = isDraftActive
    ? composerPlaceholderForAgent(draftAgentId, creators)
    : undefined;

  const updateDraftAgentId = useCallback((agentId: string) => {
    if (!activeTabKey) return;
    setTabEntries((prev) =>
      prev.map((e) =>
        tabEntryKey(e) === activeTabKey && e.kind === 'draft'
          ? { ...e, agentId }
          : e,
      ),
    );
  }, [activeTabKey]);

  const activateThread = useCallback(
    (threadId: string, opts?: { silent?: boolean; reorder?: boolean }) => {
      const thread = threads.find((t) => t.id === threadId);
      if (!thread) return;
      const entry: AgentTabEntry = { kind: 'thread', threadId };
      const key = tabEntryKey(entry);
      setTabEntries((prev) =>
        activateAgentTabEntry(prev, entry, { reorder: opts?.reorder }),
      );
      setActiveTabKey(key);
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

  const openDraftTab = useCallback((agentId = 'global') => {
    const entry = createDraftTab(agentId);
    const key = tabEntryKey(entry);
    setTabEntries((prev) => pushAgentTabEntry(prev, entry));
    setActiveTabKey(key);
  }, []);

  const handleNewDraft = useCallback(() => {
    openDraftTab('global');
  }, [openDraftTab]);

  const handleCloseTab = useCallback(
    (key: string) => {
      setTabEntries((prev) => {
        const { entries, activeKey } = closeAgentTabEntry(prev, key, activeTabKey);
        setActiveTabKey(activeKey);
        return entries;
      });
      showToast('已关闭页签', 'info');
    },
    [activeTabKey],
  );

  const handleSend = useCallback(
    async (text: string) => {
      if (activeEntry?.kind === 'draft') {
        const agentId = activeEntry.agentId;
        const draftKey = tabEntryKey(activeEntry);
        try {
          const thread =
            agentId === 'global'
              ? await createGlobalThread()
              : await createThread(agentId, sessionContext.sessionId);
          if (!thread) return;
          setTabEntries((prev) => promoteDraftTab(prev, draftKey, thread.id));
          setActiveTabKey(`thread:${thread.id}`);
          await agent.sendMessage(text, thread.id);
        } catch {
          showToast('新建会话失败', 'error');
        }
        return;
      }
      await agent.sendMessage(text);
    },
    [activeEntry, agent, createGlobalThread, createThread, sessionContext.sessionId],
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

  const removeThreadsFromTabs = useCallback((ids: string[]) => {
    const idSet = new Set(ids);
    setTabEntries((prev) => {
      let next = prev;
      for (const id of ids) {
        next = removeThreadFromTabs(next, id);
      }
      return next;
    });
    setActiveTabKey((current) => {
      if (!current?.startsWith('thread:')) return current;
      const tid = current.slice('thread:'.length);
      if (!idSet.has(tid)) return current;
      const remaining = tabEntries.filter(
        (e) => e.kind === 'thread' && !idSet.has(e.threadId),
      );
      return remaining.length ? tabEntryKey(remaining[0]!) : null;
    });
  }, [tabEntries]);

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTargetId) return;
    const id = deleteTargetId;
    setDeleteTargetId(null);
    try {
      await deleteThread(id);
      removeThreadsFromTabs([id]);
      showToast('已删除会话', 'success');
    } catch {
      showToast('删除失败', 'error');
    }
  }, [deleteTargetId, deleteThread, removeThreadsFromTabs]);

  const handleBatchDeleteConfirm = useCallback(async () => {
    if (!batchDeleteTarget) return;
    const { threadIds } = batchDeleteTarget;
    setBatchDeleteTarget(null);
    const results = await Promise.allSettled(threadIds.map((id) => deleteThread(id)));
    const succeeded = threadIds.filter((_, i) => results[i]?.status === 'fulfilled');
    const failed = threadIds.length - succeeded.length;
    if (succeeded.length) removeThreadsFromTabs(succeeded);
    if (failed > 0) {
      showToast(`已删除 ${succeeded.length} 条，${failed} 条失败`, 'error');
    } else {
      showToast(`已删除 ${succeeded.length} 条会话`, 'success');
    }
  }, [batchDeleteTarget, deleteThread, removeThreadsFromTabs]);

  const paneClass = [
    'agent-pane',
    historyCollapsed ? 'agent-history-collapsed' : '',
    agent.fatalError && agent.status === 'error' && activeThreadId ? 'agent-pane--error' : '',
  ]
    .filter(Boolean)
    .join(' ');

  if (agent.fatalError && agent.status === 'error' && activeThreadId) {
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

  const showChatMessages = Boolean(activeTabKey) && !isDraftActive;

  return (
    <section className={paneClass} aria-label="Agent" id="agent-pane">
      <AgentTabsBar
        tabEntries={tabEntries}
        threads={threads}
        creators={creators}
        activeTabKey={activeTabKey}
        historyCollapsed={historyCollapsed}
        onSelectTab={(key) => {
          setActiveTabKey(key);
          const entry = tabEntries.find((e) => tabEntryKey(e) === key);
          if (entry?.kind === 'thread') {
            activateThread(entry.threadId, { silent: true, reorder: false });
          }
        }}
        onCloseTab={handleCloseTab}
        onNewDraft={handleNewDraft}
        onToggleHistory={handleToggleHistory}
      />
      <div className="agent-body">
        <div className="agent-main">
          <div className="chat-scroll" id="chat-scroll" aria-live="polite">
            {isDraftActive ? (
              <AgentChatEmpty
                agentId={draftAgentId}
                creators={creators}
                onAgentChange={updateDraftAgentId}
              />
            ) : null}
            <div
              id="chat-live"
              style={
                playbackMode || !showChatMessages ? { display: 'none' } : undefined
              }
            >
              {!playbackMode && showChatMessages ? (
                <AgentChatMessages
                  agent={agent}
                  threadCreatorId={activeThread?.creator_id ?? null}
                />
              ) : null}
            </div>
            <div
              id="chat-playback"
              style={
                playbackMode && showChatMessages ? undefined : { display: 'none' }
              }
            >
              {playbackMode && showChatMessages ? (
                <AgentChatMessages
                  agent={agent}
                  threadCreatorId={activeThread?.creator_id ?? null}
                />
              ) : null}
            </div>
            {!activeTabKey ? (
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
            ready={composerReady}
            blocked={composerBlocked}
            model={agent.threadModel}
            providerModels={modelOptions}
            placeholder={composerPlaceholder}
            onModelChange={(m) => void agent.patchThreadModel(m)}
            onSend={(t) => void handleSend(t)}
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
              creators={creators}
              activeThreadId={activeThreadId}
              onNewGlobalDraft={() => openDraftTab('global')}
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
              onBatchDeleteRequest={(agentId, threadIds) =>
                setBatchDeleteTarget({ agentId, threadIds })
              }
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
      <ConfirmDialog
        open={batchDeleteTarget != null}
        title="批量删除会话"
        message={`确定删除该 Agent 下全部 ${batchDeleteTarget?.threadIds.length ?? 0} 条会话？此操作不可撤销。`}
        confirmLabel="删除"
        danger
        onConfirm={() => void handleBatchDeleteConfirm()}
        onCancel={() => setBatchDeleteTarget(null)}
      />
    </section>
  );
}
