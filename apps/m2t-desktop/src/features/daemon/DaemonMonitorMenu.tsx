import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useLayoutStore } from '../layout/useLayoutStore';
import { DaemonCard } from './DaemonCard';

type Props = {
  onSelectCreator: (id: string) => void;
};

function positionDaemonMenu(menu: HTMLElement, anchor: HTMLElement) {
  const rect = anchor.getBoundingClientRect();
  const menuW = Math.min(340, window.innerWidth - 16);
  let left = rect.left;
  if (left + menuW > window.innerWidth - 8) {
    left = window.innerWidth - menuW - 8;
  }
  const maxH = Math.min(520, rect.top - 16);
  menu.style.width = `${menuW}px`;
  menu.style.minWidth = '0';
  menu.style.left = `${Math.max(8, left)}px`;
  menu.style.bottom = `${window.innerHeight - rect.top + 6}px`;
  menu.style.top = 'auto';
  menu.style.maxHeight = `${Math.max(200, maxH)}px`;
}

export function DaemonMonitorMenu({ onSelectCreator }: Props) {
  const { daemonMenuOpen, setDaemonMenuOpen, leftCollapsed } = useLayoutStore();
  const menuRef = useRef<HTMLDivElement>(null);
  const [persistShell, setPersistShell] = useState(false);
  const [positionReady, setPositionReady] = useState(false);

  useEffect(() => {
    if (daemonMenuOpen && leftCollapsed) setPersistShell(true);
    if (!leftCollapsed) setPersistShell(false);
  }, [daemonMenuOpen, leftCollapsed]);

  useLayoutEffect(() => {
    if (!daemonMenuOpen || !leftCollapsed || !menuRef.current) {
      setPositionReady(false);
      return;
    }
    const anchor = document.getElementById('rail-daemon');
    if (!anchor) {
      setPositionReady(false);
      return;
    }
    positionDaemonMenu(menuRef.current, anchor);
    setPositionReady(true);

    const onRelayout = () => {
      if (!menuRef.current) return;
      const nextAnchor = document.getElementById('rail-daemon');
      if (nextAnchor) positionDaemonMenu(menuRef.current, nextAnchor);
    };
    window.addEventListener('resize', onRelayout);
    return () => window.removeEventListener('resize', onRelayout);
  }, [daemonMenuOpen, leftCollapsed, persistShell]);

  useEffect(() => {
    if (!daemonMenuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDaemonMenuOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [daemonMenuOpen, setDaemonMenuOpen]);

  if (!leftCollapsed || (!daemonMenuOpen && !persistShell)) return null;

  const pickCreator = (id: string) => {
    onSelectCreator(id);
    setDaemonMenuOpen(false);
  };

  const menuVisible = daemonMenuOpen && positionReady;

  return (
    <>
      <div
        className={`user-menu-backdrop${menuVisible ? ' open' : ''}`}
        id="daemon-menu-backdrop"
        aria-hidden={!menuVisible}
        onClick={() => setDaemonMenuOpen(false)}
      />
      <div
        ref={menuRef}
        className={`daemon-monitor-menu${menuVisible ? ' open' : ''}`}
        id="daemon-monitor-menu"
        role="dialog"
        aria-label="后台监控"
        aria-hidden={!menuVisible}
      >
        <DaemonCard onSelectCreator={pickCreator} />
      </div>
    </>
  );
}
