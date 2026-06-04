import { useLayoutStore } from './useLayoutStore';

export function UserMenu() {
  const { userMenuOpen, setUserMenuOpen, openCenterView, centerView } = useLayoutStore();

  if (!userMenuOpen) return null;

  return (
    <>
      <div
        className="user-menu-backdrop open"
        id="user-menu-backdrop"
        aria-hidden="false"
        onClick={() => setUserMenuOpen(false)}
      />
      <div className="user-menu open" id="user-menu" role="menu" aria-label="功能菜单">
        <button
          type="button"
          className={`user-menu-item${centerView === 'config' ? ' active' : ''}`}
          role="menuitem"
          data-open-view="config"
          onClick={() => openCenterView('config')}
        >
          <span className="user-menu-icon" aria-hidden="true">
            ⚙
          </span>
          <span>系统配置</span>
        </button>
        <button
          type="button"
          className={`user-menu-item${centerView === 'manage' ? ' active' : ''}`}
          role="menuitem"
          data-open-view="manage"
          onClick={() => openCenterView('manage')}
        >
          <span className="user-menu-icon" aria-hidden="true">
            ☰
          </span>
          <span>监控管理</span>
        </button>
      </div>
    </>
  );
}
