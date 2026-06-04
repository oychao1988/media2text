import { useCallback, useSyncExternalStore } from 'react';
import {
  applyLayoutCssVars,
  type CenterTab,
  type CenterView,
  DEFAULT_LAYOUT,
  loadLayout,
  saveLayout,
  type LayoutPersist,
} from './layoutConstants';

type LayoutStoreState = LayoutPersist & {
  centerView: CenterView;
  centerTab: CenterTab;
  userMenuOpen: boolean;
  creatorsLoading: boolean;
  showEmptyCreators: boolean;
};

let state: LayoutStoreState = {
  ...loadLayout(),
  centerView: 'live',
  centerTab: 'live',
  userMenuOpen: false,
  creatorsLoading: false,
  showEmptyCreators: readEmptyListPreview(),
};

const listeners = new Set<() => void>();

function readEmptyListPreview(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return new URLSearchParams(window.location.search).has('empty-list');
  } catch {
    return false;
  }
}

function emit() {
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): LayoutStoreState {
  return state;
}

function patch(partial: Partial<LayoutStoreState>) {
  const next = { ...state, ...partial };
  const layoutChanged =
    next.leftCollapsed !== state.leftCollapsed ||
    next.rightCollapsed !== state.rightCollapsed ||
    next.sidebarW !== state.sidebarW ||
    next.rightW !== state.rightW ||
    next.agentH !== state.agentH;

  state = next;
  if (layoutChanged) {
    saveLayout({
      leftCollapsed: state.leftCollapsed,
      rightCollapsed: state.rightCollapsed,
      sidebarW: state.sidebarW,
      rightW: state.rightW,
      agentH: state.agentH,
    });
    applyLayoutCssVars(state);
  }
  emit();
}

export function initLayoutStore(): void {
  applyLayoutCssVars(state);
}

export function useLayoutStore() {
  const snap = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  const setLeftCollapsed = useCallback((leftCollapsed: boolean) => {
    patch({ leftCollapsed });
  }, []);

  const setRightCollapsed = useCallback((rightCollapsed: boolean) => {
    patch({ rightCollapsed });
  }, []);

  const expandLeftPanel = useCallback(() => {
    patch({ leftCollapsed: false });
  }, []);

  const setSidebarW = useCallback((sidebarW: number) => {
    patch({ sidebarW });
  }, []);

  const setRightW = useCallback((rightW: number) => {
    patch({ rightW });
  }, []);

  const setCenterTab = useCallback((centerTab: CenterTab) => {
    patch({ centerTab, centerView: centerTab });
  }, []);

  const openCenterView = useCallback((centerView: CenterView) => {
    if (centerView === 'live' || centerView === 'history') {
      patch({ centerView, centerTab: centerView, userMenuOpen: false });
    } else {
      patch({ centerView, userMenuOpen: false });
    }
  }, []);

  const setUserMenuOpen = useCallback((userMenuOpen: boolean) => {
    patch({ userMenuOpen });
  }, []);

  const setCreatorsLoading = useCallback((creatorsLoading: boolean) => {
    patch({ creatorsLoading });
  }, []);

  return {
    ...snap,
    setLeftCollapsed,
    setRightCollapsed,
    expandLeftPanel,
    setSidebarW,
    setRightW,
    setCenterTab,
    openCenterView,
    setUserMenuOpen,
    setCreatorsLoading,
    resetLayout: () => patch({ ...DEFAULT_LAYOUT }),
  };
}
