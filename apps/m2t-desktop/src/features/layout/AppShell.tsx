import { useMemo, useState } from 'react';
import { CreatorList } from '../creators/CreatorList';
import { CreatorListEmpty } from '../creators/CreatorListEmpty';
import { CreatorListSkeleton } from '../creators/CreatorListSkeleton';
import { MOCK_CREATORS, type MockCreator } from '../creators/mockCreators';
import { CenterToolbar } from './CenterToolbar';
import { LeftRail } from './LeftRail';
import { RightRail } from './RightRail';
import { SidePanelHeader } from './SidePanelHeader';
import { useColumnResize } from './useColumnResize';
import { useLayoutStore } from './useLayoutStore';
import { UserMenu } from './UserMenu';
import { ViewConfig } from '../views/ViewConfig';
import { ViewHistory } from '../views/ViewHistory';
import { ViewLive } from '../views/ViewLive';
import { ViewManage } from '../views/ViewManage';

function readLoadingPreview(): boolean {
  try {
    return new URLSearchParams(window.location.search).has('loading');
  } catch {
    return false;
  }
}

const BADGE_BY_LIGHT: Record<MockCreator['light'], { text: string; className: string }> = {
  green: { text: '🟢 录制中', className: 'badge-recording' },
  red: { text: '🔴 在播未录', className: 'badge-live' },
  yellow: { text: '🟡 收尾中', className: 'badge-live' },
  gray: { text: '⚫ 离线', className: '' },
};

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

  const [selectedId, setSelectedId] = useState('laofanqie');
  const creatorsLoading = readLoadingPreview();

  const selected = useMemo(
    () => MOCK_CREATORS.find((c) => c.id === selectedId) ?? MOCK_CREATORS[1],
    [selectedId],
  );

  const badge = BADGE_BY_LIGHT[selected.light];
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

  return (
    <div className={appClass} id="app">
      <aside className="panel panel-left" aria-label="博主列表">
        <LeftRail selectedCreatorId={selectedId} onSelectCreator={setSelectedId} />
        <div className="left-content">
          <div className="left-main">
            <SidePanelHeader
              title="监控"
              collapseLabel="折叠左栏"
              onCollapse={() => setLeftCollapsed(true)}
            />
            {creatorsLoading ? (
              <CreatorListSkeleton />
            ) : showEmptyCreators ? (
              <CreatorListEmpty onAddCreator={() => openCenterView('manage')} />
            ) : (
              <CreatorList selectedId={selectedId} onSelect={(c) => setSelectedId(c.id)} />
            )}
          </div>
          <div className="left-daemon-wrap">
            <div className="daemon-card" id="daemon-card">
              <div className="daemon-card-head">
                <div className="daemon-status">
                  <span className="status-dot live" aria-hidden="true" />
                  <strong>Daemon 运行中</strong>
                </div>
              </div>
              <div className="daemon-meta">PID — · 静态壳（P6 接线）</div>
            </div>
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
            creatorName={selected.name}
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
              <ViewLive active={activeCreatorTab === 'live'} />
              <ViewHistory active={activeCreatorTab === 'history'} />
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
        <div className="right-content">
          <SidePanelHeader
            title="Agent"
            collapseLabel="折叠右栏"
            onCollapse={() => setRightCollapsed(true)}
          />
          <div className="right-agent-shell">
            <p className="view-shell-note">Agent / 转写面板静态壳（P7）</p>
          </div>
        </div>
      </aside>
    </div>
  );
}
