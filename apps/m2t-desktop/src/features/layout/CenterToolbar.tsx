import { useLayoutStore } from './useLayoutStore';

type Props = {
  creatorName: string;
  badge: string;
  badgeClass: string;
};

export function CenterToolbar({ creatorName, badge, badgeClass }: Props) {
  const { centerView, centerTab, setCenterTab } = useLayoutStore();
  const isSettings = centerView === 'config' || centerView === 'manage';
  const contextLabel =
    centerView === 'config' ? '系统配置' : centerView === 'manage' ? '监控管理' : '';

  return (
    <div
      className={`center-toolbar${isSettings ? ' context-settings' : ''}`}
      id="center-toolbar"
    >
      <div className="center-toolbar-left">
        {isSettings ? (
          <span className="center-context-label" id="center-context-label">
            {contextLabel}
          </span>
        ) : null}
        {!isSettings ? (
          <>
            <span className="center-title" id="center-title">
              {creatorName}
            </span>
            <span className={`badge ${badgeClass}`} id="center-badge">
              {badge}
            </span>
          </>
        ) : null}
      </div>
      {!isSettings ? (
        <div className="tabs" role="tablist" id="center-tabs" aria-label="博主视图">
          <button
            className={`tab${centerTab === 'live' ? ' active' : ''}`}
            role="tab"
            type="button"
            aria-selected={centerTab === 'live'}
            data-view="live"
            onClick={() => setCenterTab('live')}
          >
            直播
          </button>
          <button
            className={`tab${centerTab === 'history' ? ' active' : ''}`}
            role="tab"
            type="button"
            aria-selected={centerTab === 'history'}
            data-view="history"
            onClick={() => setCenterTab('history')}
          >
            历史
          </button>
        </div>
      ) : null}
    </div>
  );
}
