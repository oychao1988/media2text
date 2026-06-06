import { useCallback, useSyncExternalStore } from 'react';
import {
  applyLayoutCssVars,
  type CenterTab,
  type CenterView,
  DEFAULT_LAYOUT,
  clampAgentH,
  loadLayout,
  saveLayout,
  syncDesktopLayoutPresetClasses,
  type DesktopLayoutPreset,
  type LayoutPersist,
  transcriptChatRightW,
} from './layoutConstants';
import {
  LIVE_TRANSCRIPT_SELECTION,
  type TranscriptSelection,
} from '../transcript/transcriptSelection';
import { showToast } from '../../lib/toast';

type LayoutStoreState = LayoutPersist & {
  centerView: CenterView;
  centerTab: CenterTab;
  userMenuOpen: boolean;
  daemonMenuOpen: boolean;
  creatorsLoading: boolean;
  showEmptyCreators: boolean;
  transcriptSelection: TranscriptSelection;
};

const DESKTOP_LAYOUT_LABELS: Record<DesktopLayoutPreset, string> = {
  full: '博主 · 播放 · 转写 · 对话',
  'transcript-chat': '博主 · 转写 · 对话',
  'chat-only': '博主 · 对话',
};

let state: LayoutStoreState = {
  ...loadLayout(),
  centerView: 'live',
  centerTab: 'live',
  userMenuOpen: false,
  daemonMenuOpen: false,
  creatorsLoading: false,
  showEmptyCreators: readEmptyListPreview(),
  transcriptSelection: LIVE_TRANSCRIPT_SELECTION,
};

applyLayoutCssVars(state);

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
    next.agentH !== state.agentH ||
    next.desktopLayoutPreset !== state.desktopLayoutPreset ||
    next.agentHistoryW !== state.agentHistoryW;

  state = next;
  if (layoutChanged) {
    saveLayout({
      leftCollapsed: state.leftCollapsed,
      rightCollapsed: state.rightCollapsed,
      sidebarW: state.sidebarW,
      rightW: state.rightW,
      agentH: state.agentH,
      desktopLayoutPreset: state.desktopLayoutPreset,
      agentHistoryW: state.agentHistoryW,
    });
    applyLayoutCssVars(state);
    syncDesktopLayoutPresetClasses(state.desktopLayoutPreset);
  }
  emit();
}

export function initLayoutStore(): void {
  const agentH = clampAgentH(state.agentH);
  if (agentH !== state.agentH) {
    state = { ...state, agentH };
  }
  applyLayoutCssVars(state);
  syncDesktopLayoutPresetClasses(state.desktopLayoutPreset);
  if (state.desktopLayoutPreset === 'chat-only' && state.rightCollapsed) {
    patch({ rightCollapsed: false });
  }
}

/** Persist pane sizes after drag (skipped during pointermove for smoothness). */
export function commitLayoutSizes(
  sizes: Partial<Pick<LayoutPersist, 'sidebarW' | 'rightW' | 'agentH' | 'agentHistoryW'>>,
): void {
  const next = { ...sizes };
  if (next.agentH != null) {
    next.agentH = clampAgentH(next.agentH);
  }
  patch(next);
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
    patch({ userMenuOpen, daemonMenuOpen: userMenuOpen ? false : state.daemonMenuOpen });
  }, []);

  const setDaemonMenuOpen = useCallback((daemonMenuOpen: boolean) => {
    patch({ daemonMenuOpen, userMenuOpen: daemonMenuOpen ? false : state.userMenuOpen });
  }, []);

  const setCreatorsLoading = useCallback((creatorsLoading: boolean) => {
    patch({ creatorsLoading });
  }, []);

  const setDesktopLayoutPreset = useCallback((desktopLayoutPreset: DesktopLayoutPreset) => {
    const partial: Partial<LayoutStoreState> = { desktopLayoutPreset };
    if (desktopLayoutPreset === 'chat-only' && state.rightCollapsed) {
      partial.rightCollapsed = false;
    }
    if (desktopLayoutPreset === 'transcript-chat') {
      partial.rightW = transcriptChatRightW(state.sidebarW);
    }
    patch(partial);
    showToast(`布局：${DESKTOP_LAYOUT_LABELS[desktopLayoutPreset]}`, 'info');
  }, []);

  const setTranscriptSelection = useCallback((transcriptSelection: TranscriptSelection) => {
    patch({ transcriptSelection });
  }, []);

  const setAgentHistoryW = useCallback((agentHistoryW: number) => {
    patch({ agentHistoryW });
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
    setDaemonMenuOpen,
    setCreatorsLoading,
    setDesktopLayoutPreset,
    setTranscriptSelection,
    setAgentHistoryW,
    resetLayout: () => patch({ ...DEFAULT_LAYOUT, transcriptSelection: LIVE_TRANSCRIPT_SELECTION }),
  };
}
