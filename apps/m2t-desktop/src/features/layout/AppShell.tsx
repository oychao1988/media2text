import { useCallback, useMemo, useState } from 'react';
import { CreatorList } from '../creators/CreatorList';
import { CreatorListEmpty } from '../creators/CreatorListEmpty';
import { CreatorListSkeleton } from '../creators/CreatorListSkeleton';
import { useCreators } from '../creators/CreatorsContext';
import { DaemonCard } from '../daemon/DaemonCard';
import { ViewPlayback } from '../history/ViewPlayback';
import { useLiveStatus } from '../live/useLiveStatus';
import { AgentPanel } from '../agent/AgentPanel';
import { TranscriptPane } from '../transcript/TranscriptPane';
import { TranscriptSessionSelect } from '../transcript/TranscriptSessionSelect';
import type { LiveSessionSummary } from '../../lib/types';
import { ViewConfig } from '../views/ViewConfig';
import { ViewHistory } from '../views/ViewHistory';
import { ViewLive } from '../views/ViewLive';
import { ViewManage } from '../views/ViewManage';
import { CenterToolbar } from './CenterToolbar';
import { DesktopLayoutPresets } from './DesktopLayoutPresets';
import { LeftRail } from './LeftRail';
import { RightRail } from './RightRail';
import { SidePanelHeader } from './SidePanelHeader';
import { useColumnResize } from './useColumnResize';
import { useRowResize } from './useRowResize';
import { useLayoutStore } from './useLayoutStore';
import { UserMenu } from './UserMenu';
import { USER_DISPLAY_NAME, userDisplayInitial } from './userDisplay';

function readLoadingPreview(): boolean {
  try {
    return new URLSearchParams(window.location.search).has('loading');
  } catch {
    return false;
  }
}

export function AppShell() {
  const {
    leftCollapsed,
    rightCollapsed,
    setLeftCollapsed,
    setRightCollapsed,
    centerView,
    centerTab,
    openCenterView,
    setUserMenuOpen,
    userMenuOpen,
    showEmptyCreators,
    desktopLayoutPreset,
    transcriptSelection,
  } = useLayoutStore();

  const {
    creators,
    loading: creatorsLoading,
    error: creatorsError,
    selectedId,
    selected,
    setSelectedId,
    refresh: refreshCreators,
  } = useCreators();

  const [playbackSession, setPlaybackSession] = useState<LiveSessionSummary | null>(null);
  const [playbackTime, setPlaybackTime] = useState(0);
  const previewLoading = readLoadingPreview();
  const { refresh: refreshLive } = useLiveStatus(
    centerView === 'live' || centerView === 'history' || centerView === 'playback'
      ? selectedId
      : null,
  );

  const badge = selected
    ? { text: selected.badge, className: selected.badge_class }
    : { text: '', className: '' };

  const resize = useColumnResize();
  const rowResize = useRowResize();

  const isTranscriptChat = desktopLayoutPreset === 'transcript-chat';
  const isChatOnly = desktopLayoutPreset === 'chat-only';
  const showTranscriptPane = !isChatOnly;

  const appClass = [
    'app',
    leftCollapsed ? 'left-collapsed' : '',
    rightCollapsed ? 'right-collapsed' : '',
    leftCollapsed && rightCollapsed ? 'both-collapsed' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const showCreatorContext =
    centerView === 'live' || centerView === 'history' || centerView === 'playback';
  const activeCreatorTab =
    centerView === 'playback' ? 'history' : centerView === 'history' ? 'history' : centerTab;
  const showRecordBanner = selected?.status_light === 'red';

  const keepLiveStream =
    (centerView === 'live' || centerView === 'history') &&
    Boolean(selected?.active_session_id);

  const historySessionRow = useMemo(() => {
    if (transcriptSelection.mode !== 'history' || !selectedId) return null;
    return {
      creatorId: selectedId,
      kind: transcriptSelection.kind,
      itemId: transcriptSelection.itemId,
    };
  }, [selectedId, transcriptSelection]);

  const transcriptSessionId = useMemo(() => {
    if (historySessionRow) {
      return historySessionRow.kind === 'live' ? historySessionRow.itemId : null;
    }
    if (centerView === 'playback' && playbackSession) return playbackSession.session_id;
    if (centerView === 'live' || centerTab === 'live') return selected?.active_session_id ?? null;
    return null;
  }, [centerView, centerTab, historySessionRow, playbackSession, selected]);

  const summaryPath = useMemo(() => {
    if (historySessionRow && transcriptSelection.mode === 'history') {
      return null;
    }
    if (centerView === 'playback' && playbackSession) return playbackSession.summary_path;
    return null;
  }, [centerView, historySessionRow, playbackSession, transcriptSelection.mode]);

  const transcriptPath = useMemo(() => {
    if (historySessionRow && transcriptSelection.mode === 'history') {
      return null;
    }
    if (centerView === 'playback' && playbackSession) return playbackSession.transcript_path;
    return null;
  }, [centerView, historySessionRow, playbackSession, transcriptSelection.mode]);

  const playbackItem = useMemo(() => {
    if (historySessionRow) {
      return {
        creatorId: historySessionRow.creatorId,
        kind: historySessionRow.kind,
        itemId: historySessionRow.itemId,
        hasTranscript: true,
        hasSummary: true,
      };
    }
    if (centerView === 'playback' && playbackSession && selectedId) {
      return {
        creatorId: selectedId,
        kind: playbackSession.kind,
        itemId: playbackSession.session_id,
        hasTranscript: playbackSession.has_transcript,
        hasSummary: playbackSession.has_summary,
      };
    }
    return null;
  }, [centerView, historySessionRow, playbackSession, selectedId]);

  const transcriptMode =
    historySessionRow || centerView === 'playback' ? ('playback' as const) : ('live' as const);

  const rightPanelTitle = isTranscriptChat ? 'Agent' : '内容';

  const listLoading = previewLoading || creatorsLoading;
  const listEmpty = !listLoading && !creatorsError && (showEmptyCreators || creators.length === 0);

  const handleHistorySessionSelect = (session: LiveSessionSummary) => {
    setPlaybackSession(session);
    openCenterView('playback');
  };

  const handleSelectCreator = useCallback(
    (id: string) => {
      const creator = creators.find((c) => c.id === id);
      const isLive = creator != null && (creator.is_live || creator.status_light === 'green');
      const targetView = isLive ? 'live' : 'history';

      setSelectedId(id);
      if (centerView === 'config' || centerView === 'manage' || centerView === 'playback') {
        if (centerView === 'playback') setPlaybackSession(null);
        openCenterView(targetView);
      } else if (centerView === 'live' || centerView === 'history') {
        openCenterView(targetView);
      }
    },
    [centerView, creators, openCenterView, setSelectedId],
  );

  const transcriptPaneKey = historySessionRow
    ? `history-${historySessionRow.kind}-${historySessionRow.itemId}`
    : `live-${transcriptSessionId ?? 'none'}`;

  const transcriptPane = showTranscriptPane ? (
    <TranscriptPane
      key={transcriptPaneKey}
      sessionId={transcriptSessionId}
      summaryPath={summaryPath}
      transcriptPath={transcriptPath}
      mode={transcriptMode}
      playbackTime={playbackTime}
      playbackItem={playbackItem}
      onSummaryUpdated={(path) => {
        if (!playbackSession) return;
        setPlaybackSession({ ...playbackSession, has_summary: Boolean(path), summary_path: path });
      }}
    />
  ) : null;

  return (
    <div className={appClass} id="app">
      <aside className="panel panel-left" aria-label="博主列表">
        <LeftRail
          creators={creators}
          selectedCreatorId={selectedId}
          onSelectCreator={handleSelectCreator}
        />
        <div className="left-content">
          <div className="left-main">
            <SidePanelHeader
              title="监控"
              side="left"
              collapseLabel="折叠左栏"
              onCollapse={() => setLeftCollapsed(true)}
            />
            {listLoading ? (
              <CreatorListSkeleton />
            ) : listEmpty ? (
              <CreatorListEmpty onAddCreator={() => openCenterView('manage')} />
            ) : (
              <CreatorList
                creators={creators}
                selectedId={selectedId}
                loading={listLoading}
                error={creatorsError}
                onSelect={(c) => handleSelectCreator(c.id)}
                onRetry={() => void refreshCreators()}
              />
            )}
          </div>
          <div className="left-daemon-wrap">
            <DaemonCard onSelectCreator={handleSelectCreator} />
          </div>
          <div className="left-user-wrap">
            <button
              type="button"
              className="left-user-bar"
              id="user-menu-trigger"
              aria-haspopup="menu"
              aria-expanded={userMenuOpen}
              aria-controls="user-menu"
              onClick={() => setUserMenuOpen(!userMenuOpen)}
            >
              <div className="avatar" aria-hidden="true">
                {userDisplayInitial()}
              </div>
              <div className="user-meta">
                <span className="user-name">{USER_DISPLAY_NAME}</span>
                <span className="user-hint">系统配置 · 监控管理</span>
              </div>
              <span className="user-chevron" aria-hidden="true">
                ▲
              </span>
            </button>
          </div>
        </div>
        <UserMenu />
      </aside>

      <div
        className="col-resize col-resize-left"
        id="resize-left"
        role="separator"
        aria-orientation="vertical"
        aria-label="调整左栏宽度"
        tabIndex={0}
        onPointerDown={resize.onLeftPointerDown}
        onPointerMove={resize.onLeftPointerMove}
        onPointerUp={resize.onLeftPointerUp}
      />

      <main className="center" aria-label="主展示区">
        {isTranscriptChat && showTranscriptPane ? (
          <div className="transcript-center-slot" id="transcript-center-slot">
            <SidePanelHeader
              title="转写"
              side="right"
              collapseLabel="折叠右栏"
              onCollapse={() => setRightCollapsed(true)}
              actions={
                <>
                  <TranscriptSessionSelect />
                  <DesktopLayoutPresets />
                </>
              }
            />
            {transcriptPane}
          </div>
        ) : (
          <>
            {showCreatorContext ? (
              <CenterToolbar
                creatorName={selected?.display_name ?? ''}
                badge={badge.text}
                badgeClass={badge.className}
                hideTabs={centerView === 'playback'}
              />
            ) : (
              <CenterToolbar creatorName="" badge="" badgeClass="" hideTabs={false} />
            )}
            <div className="center-body" id="center-body">
              {centerView === 'config' ? (
                <ViewConfig />
              ) : centerView === 'manage' ? (
                <ViewManage />
              ) : (
                <>
                  <ViewLive
                    active={activeCreatorTab === 'live' && centerView !== 'playback'}
                    keepStream={keepLiveStream}
                    creatorId={selectedId}
                    showRecordBanner={showRecordBanner}
                    onRecordingStarted={() => void refreshLive()}
                  />
                  <ViewHistory
                    active={activeCreatorTab === 'history' && centerView !== 'playback'}
                    creatorId={selectedId}
                    onSessionSelect={handleHistorySessionSelect}
                  />
                  <ViewPlayback
                    active={centerView === 'playback'}
                    creatorName={selected?.display_name ?? ''}
                    session={playbackSession}
                    onTimeUpdate={setPlaybackTime}
                  />
                </>
              )}
            </div>
          </>
        )}
      </main>

      <div
        className="col-resize col-resize-right"
        id="resize-right"
        role="separator"
        aria-orientation="vertical"
        aria-label="调整右栏宽度"
        tabIndex={0}
        onPointerDown={resize.onRightPointerDown}
        onPointerMove={resize.onRightPointerMove}
        onPointerUp={resize.onRightPointerUp}
      />

      <aside className="panel panel-right" aria-label="转写与 Agent">
        <RightRail />
        <div className="right-content right-split">
          <SidePanelHeader
            title={rightPanelTitle}
            side="right"
            collapseLabel="折叠右栏"
            onCollapse={() => setRightCollapsed(true)}
            actions={
              !isTranscriptChat ? (
                <>
                  {showTranscriptPane ? <TranscriptSessionSelect /> : null}
                  <DesktopLayoutPresets />
                </>
              ) : null
            }
          />
          {!isTranscriptChat && showTranscriptPane ? transcriptPane : null}
          {!isChatOnly ? (
            <div
              className="row-resize"
              id="resize-right-split"
              role="separator"
              aria-orientation="horizontal"
              aria-label="调整 Agent 区域高度"
              tabIndex={0}
              onPointerDown={rowResize.onPointerDown}
              onPointerMove={rowResize.onPointerMove}
              onPointerUp={rowResize.onPointerUp}
            />
          ) : null}
          <AgentPanel
            creatorId={selectedId}
            sessionId={transcriptSessionId}
            playbackMode={transcriptMode === 'playback'}
          />
        </div>
      </aside>
    </div>
  );
}
