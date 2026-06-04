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

const PANEL_TOGGLE_MS = 250;

function withPanelToggle(apply: () => void) {
  const app = document.getElementById('app');
  app?.classList.add('panel-toggling');
  apply();
  window.setTimeout(() => app?.classList.remove('panel-toggling'), PANEL_TOGGLE_MS);
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

/** Persist pane sizes after drag (skipped during pointermove for smoothness). */
export function commitLayoutSizes(
  sizes: Partial<Pick<LayoutPersist, 'sidebarW' | 'rightW' | 'agentH'>>,
): void {
  patch(sizes);
}

export function useLayoutStore() {
  const snap = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  const setLeftCollapsed = useCallback((leftCollapsed: boolean) => {
    withPanelToggle(() => patch({ leftCollapsed }));
  }, []);

  const setRightCollapsed = useCallback((rightCollapsed: boolean) => {
    patch({ rightCollapsed });
  }, []);

  const expandLeftPanel = useCallback(() => {
    withPanelToggle(() => patch({ leftCollapsed: false }));
  }, []);

  const setSidebarW = useCallback((sidebarW: number) => {
    patch({ sidebarW });
  }, []);

  const setRightW = useCallback((rightW: number) => {
    patch({ rightW });
  }, []);

  const setAgentH = useCallback((agentH: number) => {
    patch({ agentH });
  }, []);

  const setCenterTab = useCallback((centerTab: CenterTab) => {
    patch({ centerTab, centerView: centerTab, userMenuOpen: false });
  }, []);

  const openCenterView = useCallback((centerView: CenterView) => {
    if (centerView === 'live' || centerView === 'history') {
      patch({ centerView, centerTab: centerView, userMenuOpen: false });
    } else {
      patch({ centerView, userMenuOpen: false });
    }
  }, []);

  const backToHistory = useCallback(() => {
    patch({ centerView: 'history', centerTab: 'history', userMenuOpen: false });
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
    setAgentH,
    setCenterTab,
    openCenterView,
    backToHistory,
    setUserMenuOpen,
    setCreatorsLoading,
    resetLayout: () => patch({ ...DEFAULT_LAYOUT }),
  };
}
