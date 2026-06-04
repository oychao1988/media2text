export const LAYOUT_STORAGE_KEY = 'm2t-desktop-layout';

export const SIZE_DEFAULTS = {
  sidebarW: 240,
  rightW: 360,
  agentH: 320,
} as const;

export const SIZE_LIMITS = {
  sidebar: { min: 180, max: 420 },
  right: { min: 280, max: 9999 },
  center: { min: 100 },
  agent: { min: 160, max: 720 },
  transcriptMin: 100,
} as const;

export type CenterTab = 'live' | 'history';
export type CenterView = CenterTab | 'playback' | 'config' | 'manage';

export type LayoutPersist = {
  leftCollapsed: boolean;
  rightCollapsed: boolean;
  sidebarW: number;
  rightW: number;
  agentH: number;
};

export const DEFAULT_LAYOUT: LayoutPersist = {
  leftCollapsed: false,
  rightCollapsed: false,
  sidebarW: SIZE_DEFAULTS.sidebarW,
  rightW: SIZE_DEFAULTS.rightW,
  agentH: SIZE_DEFAULTS.agentH,
};

export function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}

export function loadLayout(): LayoutPersist {
  try {
    const raw = localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_LAYOUT };
    const parsed = JSON.parse(raw) as Partial<LayoutPersist>;
    return {
      leftCollapsed: Boolean(parsed.leftCollapsed),
      rightCollapsed: Boolean(parsed.rightCollapsed),
      sidebarW: clamp(
        Number(parsed.sidebarW) || SIZE_DEFAULTS.sidebarW,
        SIZE_LIMITS.sidebar.min,
        SIZE_LIMITS.sidebar.max,
      ),
      rightW: clamp(
        Number(parsed.rightW) || SIZE_DEFAULTS.rightW,
        SIZE_LIMITS.right.min,
        SIZE_LIMITS.right.max,
      ),
      agentH: clamp(
        Number(parsed.agentH) || SIZE_DEFAULTS.agentH,
        SIZE_LIMITS.agent.min,
        SIZE_LIMITS.agent.max,
      ),
    };
  } catch {
    return { ...DEFAULT_LAYOUT };
  }
}

export function saveLayout(layout: LayoutPersist): void {
  try {
    localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layout));
  } catch {
    /* ignore */
  }
}

export function applyLayoutCssVars(layout: LayoutPersist): void {
  const root = document.documentElement;
  root.style.setProperty('--sidebar-w', `${layout.sidebarW}px`);
  root.style.setProperty('--right-w', `${layout.rightW}px`);
  root.style.setProperty('--right-agent-h', `${layout.agentH}px`);
}
