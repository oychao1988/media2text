import { useLayoutEffect, useRef } from 'react';
import { useLayoutStore } from './useLayoutStore';

function positionUserMenu(
  menu: HTMLElement,
  anchor: HTMLElement,
  leftCollapsed: boolean,
  sidebarW: number,
) {
  const rect = anchor.getBoundingClientRect();
  const menuW = leftCollapsed
    ? Math.min(200, window.innerWidth - 16)
    : Math.min(rect.width, sidebarW - 16, window.innerWidth - 16);
  let left = rect.left;
  if (left + menuW > window.innerWidth - 8) {
    left = window.innerWidth - menuW - 8;
  }
  menu.style.width = `${menuW}px`;
  menu.style.minWidth = '0';
  menu.style.left = `${Math.max(8, left)}px`;
  menu.style.bottom = `${window.innerHeight - rect.top + 6}px`;
  menu.style.top = 'auto';
}

export function UserMenu() {
  const { userMenuOpen, setUserMenuOpen, openCenterView, centerView, leftCollapsed, sidebarW } =
    useLayoutStore();
  const menuRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!userMenuOpen || !menuRef.current) return;
    const anchor = document.getElementById(leftCollapsed ? 'rail-user-menu' : 'user-menu-trigger');
    if (!anchor) return;
    positionUserMenu(menuRef.current, anchor, leftCollapsed, sidebarW);

    const onRelayout = () => {
      if (!menuRef.current) return;
      const nextAnchor = document.getElementById(
        leftCollapsed ? 'rail-user-menu' : 'user-menu-trigger',
      );
      if (nextAnchor) positionUserMenu(menuRef.current, nextAnchor, leftCollapsed, sidebarW);
    };
    window.addEventListener('resize', onRelayout);
    return () => window.removeEventListener('resize', onRelayout);
  }, [userMenuOpen, leftCollapsed, sidebarW]);

  if (!userMenuOpen) return null;

  return (
    <>
      <div
        className="user-menu-backdrop open"
        id="user-menu-backdrop"
        aria-hidden="false"
        onClick={() => setUserMenuOpen(false)}
      />
      <div
        ref={menuRef}
        className="user-menu open"
        id="user-menu"
        role="menu"
        aria-label="功能菜单"
      >
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
