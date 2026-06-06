import { useCallback, useEffect, useMemo, useState } from 'react';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { showToast, showToastWithAction } from '../../lib/toast';
import { useCreators } from '../creators/CreatorsContext';
import { positionAgentContextMenu } from './contextMenuPosition';
import { AgentChatEmpty, composerPlaceholderForAgent } from './AgentChatEmpty';
import { AgentHistorySidebar } from './AgentHistorySidebar';
import { AgentTabsBar } from './AgentTabsBar';
import { AgentThreadContextMenu } from './AgentThreadContextMenu';
import { shouldNotifyCreatorMismatch } from './agentThreadSelect';
import { buildAgentModelCatalog } from './agentModelCatalog';
import { resolveAgentProfile, sidebarAgentId } from './agentProfile';
import { ChatMessageAgent } from './ChatMessageAgent';
import { ChatMessageUser } from './ChatMessageUser';
import { AgentComposer } from './AgentComposer';
import { ToolResultCard } from './ToolResultCard';
import { useAgentHistoryResize } from './useAgentHistoryResize';
import { useAgentChatScroll } from './useAgentChatScroll';
import {
  activateAgentTabEntry,
  closeAgentTabEntry,
  openOrFocusDraftTab,
  promoteDraftTab,
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
          const payload = msg.result.payload;
          if (payload.ok) return null;
          return (
            <div key={msg.id} className="chat-msg-tool">
              <ToolResultCard result={payload} toolName={msg.toolName} />
            </div>
          );
        }
        return (
          <ChatMessageAgent
            key={msg.id}
            profile={agentProfile}
            creators={creators}
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
          creators={creators}
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
  const { threads, createThread, createGlobalThread, renameThread, deleteThread, refresh, applyThreadTitle } =
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
  const defaultAgentId = sidebarAgentId(creatorId);

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

  const creatorMismatch =
    !isDraftActive && shouldNotifyCreatorMismatch(activeThread?.creator_id, creatorId);

  const agent = useM2tAgent({
    threadId: activeThreadId,
    creatorId,
    threadCreatorId: activeThread?.creator_id ?? null,
    sessionContext,
    onTurnEnd: refresh,
    onThreadTitle: applyThreadTitle,
  });

  const { scrollRef: chatScrollRef, onScroll: onChatScroll } = useAgentChatScroll(
    activeThreadId,
    [
      activeThreadId,
      agent.messages,
      agent.activeTurn?.assistantText,
      agent.activeTurn?.phaseLabel,
      agent.activeTurn?.thinkingText,
      agent.status,
    ],
  );

  const { models: modelOptions, providerByModel } = useMemo(
    () => buildAgentModelCatalog(agent.providers),
    [agent.providers],
  );

  const composerReady = agent.ready;
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

  useEffect(() => {
    if (tabEntries.length > 0) return;
    const { entries, activeKey } = openOrFocusDraftTab([], defaultAgentId);
    setTabEntries(entries);
    setActiveTabKey(activeKey);
  }, [defaultAgentId, tabEntries.length]);

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
    setTabEntries((prev) => {
      const { entries, activeKey } = openOrFocusDraftTab(prev, agentId);
      setActiveTabKey(activeKey);
      return entries;
    });
  }, []);

  const handleNewDraft = useCallback(() => {
    openDraftTab(defaultAgentId);
  }, [defaultAgentId, openDraftTab]);

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
          const model = agent.threadModel;
          const providerName = model === 'auto' ? undefined : providerByModel.get(model);
          const threadOpts = { model, providerName };
          const thread =
            agentId === 'global'
              ? await createGlobalThread(threadOpts)
              : await createThread(agentId, sessionContext.sessionId, threadOpts);
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
    [activeEntry, agent, createGlobalThread, createThread, providerByModel, sessionContext.sessionId],
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
          <div
            className="chat-scroll"
            id="chat-scroll"
            ref={chatScrollRef}
            onScroll={onChatScroll}
            aria-live="polite"
          >
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
            {creatorMismatch ? (
              <div
                className="agent-mismatch-banner"
                id="agent-mismatch-banner"
                role="status"
              >
                <span>该会话属于其他博主，与左侧当前选中的博主不同，仍可继续对话。</span>
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
            blocked={false}
            model={agent.threadModel}
            providerModels={modelOptions}
            placeholder={composerPlaceholder}
            onModelChange={(m) =>
              void agent.patchThreadModel(m, m === 'auto' ? null : providerByModel.get(m))
            }
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
