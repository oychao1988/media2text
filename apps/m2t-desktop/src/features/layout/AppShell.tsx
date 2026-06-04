import { useMemo, useState } from 'react';
import { CreatorList } from '../creators/CreatorList';
import { CreatorListEmpty } from '../creators/CreatorListEmpty';
import { CreatorListSkeleton } from '../creators/CreatorListSkeleton';
import { useCreators } from '../creators/CreatorsContext';
import { DaemonCard } from '../daemon/DaemonCard';
import { useLiveStatus } from '../live/useLiveStatus';
import { TranscriptPane } from '../transcript/TranscriptPane';
import type { LiveSessionSummary } from '../../lib/types';
import { ViewConfig } from '../views/ViewConfig';
import { ViewHistory } from '../views/ViewHistory';
import { ViewLive } from '../views/ViewLive';
import { ViewManage } from '../views/ViewManage';
import { CenterToolbar } from './CenterToolbar';
import { LeftRail } from './LeftRail';
import { RightRail } from './RightRail';
import { SidePanelHeader } from './SidePanelHeader';
import { useColumnResize } from './useColumnResize';
import { useLayoutStore } from './useLayoutStore';
import { UserMenu } from './UserMenu';

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

  const [historySession, setHistorySession] = useState<LiveSessionSummary | null>(null);
  const previewLoading = readLoadingPreview();
  const { activeSessionId, refresh: refreshLive } = useLiveStatus(
    centerView === 'live' || centerView === 'history' ? selectedId : null,
  );

  const badge = selected
    ? { text: selected.badge, className: selected.badge_class }
    : { text: '', className: '' };

  const resize = useColumnResize();

  const appClass = [
    'app',
    leftCollapsed ? 'left-collapsed' : '',
    rightCollapsed ? 'right-collapsed' : '',
    leftCollapsed && rightCollapsed ? 'both-collapsed' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const showCreatorContext = centerView === 'live' || centerView === 'history';
  const activeCreatorTab = centerView === 'history' ? 'history' : centerTab;
  const showRecordBanner = selected?.status_light === 'red';

  const transcriptSessionId = useMemo(() => {
    if (centerView === 'history' && historySession) return historySession.session_id;
    if (centerView === 'live' || centerTab === 'live') return activeSessionId;
    return null;
  }, [centerView, centerTab, historySession, activeSessionId]);

  const summaryPath = useMemo(() => {
    if (centerView === 'history' && historySession) return historySession.summary_path;
    return null;
  }, [centerView, historySession]);

  const listLoading = previewLoading || creatorsLoading;
  const listEmpty = !listLoading && !creatorsError && (showEmptyCreators || creators.length === 0);

  return (
    <div className={appClass} id="app">
      <aside className="panel panel-left" aria-label="博主列表">
        <LeftRail
          creators={creators}
          selectedCreatorId={selectedId}
          onSelectCreator={setSelectedId}
        />
        <div className="left-content">
          <div className="left-main">
            <SidePanelHeader
              title="监控"
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
                onSelect={(c) => setSelectedId(c.id)}
                onRetry={() => void refreshCreators()}
              />
            )}
          </div>
          <div className="left-daemon-wrap">
            <DaemonCard />
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
                O
              </div>
              <div className="user-meta">
                <span className="user-name">Oychao</span>
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
        {showCreatorContext ? (
          <CenterToolbar
            creatorName={selected?.display_name ?? ''}
            badge={badge.text}
            badgeClass={badge.className}
          />
        ) : (
          <CenterToolbar creatorName="" badge="" badgeClass="" />
        )}
        <div className="center-body" id="center-body">
          {centerView === 'config' ? (
            <ViewConfig />
          ) : centerView === 'manage' ? (
            <ViewManage />
          ) : (
            <>
              <ViewLive
                active={activeCreatorTab === 'live'}
                creatorId={selectedId}
                showRecordBanner={showRecordBanner}
                onRecordingStarted={() => void refreshLive()}
              />
              <ViewHistory
                active={activeCreatorTab === 'history'}
                creatorId={selectedId}
                onSessionSelect={setHistorySession}
              />
            </>
          )}
        </div>
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
            title="内容"
            collapseLabel="折叠右栏"
            onCollapse={() => setRightCollapsed(true)}
          />
          <TranscriptPane
            sessionId={transcriptSessionId}
            summaryPath={summaryPath}
            mode={centerView === 'history' ? 'playback' : 'live'}
          />
          <div className="right-agent-shell">
            <p className="view-shell-note">Agent 面板（P7 #132）</p>
          </div>
        </div>
      </aside>
    </div>
  );
}
