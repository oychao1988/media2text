export const LAYOUT_STORAGE_KEY = 'm2t-desktop-layout';

export const SIZE_DEFAULTS = {
  sidebarW: 240,
  rightW: 360,
  agentH: 320,
  agentHistoryW: 200,
} as const;

export const SIZE_LIMITS = {
  sidebar: { min: 180, max: 420 },
  right: { min: 280, max: 9999 },
  /** JS clamp fallback; CSS uses --center-min-w (25vw). */
  center: { min: 100 },
  agent: { min: 160, max: 720 },
  agentHistory: { min: 140, max: 340 },
  transcriptMin: 100,
} as const;

export type DesktopLayoutPreset = 'full' | 'transcript-chat' | 'chat-only';

export type CenterTab = 'live' | 'history';
export type CenterView = CenterTab | 'playback' | 'config' | 'manage';

export type LayoutPersist = {
  leftCollapsed: boolean;
  rightCollapsed: boolean;
  sidebarW: number;
  rightW: number;
  agentH: number;
  desktopLayoutPreset: DesktopLayoutPreset;
  agentHistoryW: number;
};

export const DEFAULT_LAYOUT: LayoutPersist = {
  leftCollapsed: false,
  rightCollapsed: false,
  sidebarW: SIZE_DEFAULTS.sidebarW,
  rightW: SIZE_DEFAULTS.rightW,
  agentH: SIZE_DEFAULTS.agentH,
  desktopLayoutPreset: 'full',
  agentHistoryW: SIZE_DEFAULTS.agentHistoryW,
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
      desktopLayoutPreset:
        parsed.desktopLayoutPreset === 'transcript-chat' ||
        parsed.desktopLayoutPreset === 'chat-only'
          ? parsed.desktopLayoutPreset
          : 'full',
      agentHistoryW: clamp(
        Number(parsed.agentHistoryW) || SIZE_DEFAULTS.agentHistoryW,
        SIZE_LIMITS.agentHistory.min,
        SIZE_LIMITS.agentHistory.max,
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
  root.style.setProperty('--agent-history-w', `${layout.agentHistoryW}px`);
}

export function syncDesktopLayoutPresetClasses(preset: DesktopLayoutPreset): void {
  const app = document.getElementById('app');
  if (!app) return;
  app.classList.remove(
    'desktop-layout-full',
    'desktop-layout-transcript',
    'desktop-layout-chat-only',
    'desktop-layout-chat',
  );
  if (preset === 'transcript-chat') {
    app.classList.add('desktop-layout-transcript');
  } else if (preset === 'chat-only') {
    app.classList.add('desktop-layout-chat-only', 'desktop-layout-chat');
  } else {
    app.classList.add('desktop-layout-full');
  }
}

function readCssPx(varName: string, fallback: number): number {
  const v = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(varName));
  return Number.isFinite(v) ? v : fallback;
}

/** Minimum center column width from --center-min-w (supports px or vw). */
export function readCenterMinPx(): number {
  if (typeof window === 'undefined') return 320;
  const raw = getComputedStyle(document.documentElement).getPropertyValue('--center-min-w').trim();
  if (raw.endsWith('vw')) {
    const vw = parseFloat(raw);
    return Number.isFinite(vw) ? Math.floor((window.innerWidth * vw) / 100) : Math.floor(window.innerWidth * 0.25);
  }
  const px = parseFloat(raw);
  return Number.isFinite(px) ? px : Math.floor(window.innerWidth * 0.25);
}

function readGripPx(): number {
  return readCssPx('--grip-w', 6);
}

/** Max sidebar width that still leaves center at least readCenterMinPx(). */
export function maxSidebarWForViewport(rightW?: number): number {
  const rw = rightW ?? readCssPx('--right-w', SIZE_DEFAULTS.rightW);
  const available = window.innerWidth - readCenterMinPx() - readGripPx() * 2 - rw;
  return Math.max(SIZE_LIMITS.sidebar.min, Math.min(SIZE_LIMITS.sidebar.max, available));
}

/** Max right width that still leaves center at least readCenterMinPx(). */
export function maxRightWForViewport(sidebarW?: number): number {
  const sw = sidebarW ?? readCssPx('--sidebar-w', SIZE_DEFAULTS.sidebarW);
  const available = window.innerWidth - readCenterMinPx() - readGripPx() * 2 - sw;
  const halfMax = Math.floor(window.innerWidth * 0.5);
  return Math.max(SIZE_LIMITS.right.min, Math.min(halfMax, SIZE_LIMITS.right.max, available));
}

/** Split remaining width between center transcript and right agent columns. */
export function maxCenterRightWForTranscriptLayout(sidebarW?: number): number {
  const sw = sidebarW ?? readCssPx('--sidebar-w', SIZE_DEFAULTS.sidebarW);
  const grips = readGripPx() * 2;
  const remaining = window.innerWidth - sw - grips;
  const minCenter = Math.max(SIZE_LIMITS.center.min, 280);
  const minRight = SIZE_LIMITS.right.min;
  const half = Math.floor(remaining / 2);
  return Math.max(minRight, Math.min(half, remaining - minCenter));
}

/** Update pane CSS vars during drag without localStorage or React re-renders. */
export function applyLayoutSizesTransient(
  partial: Partial<Pick<LayoutPersist, 'sidebarW' | 'rightW' | 'agentH'>>,
): void {
  const root = document.documentElement;
  const sidebarW = partial.sidebarW ?? readCssPx('--sidebar-w', SIZE_DEFAULTS.sidebarW);
  const rightW = partial.rightW ?? readCssPx('--right-w', SIZE_DEFAULTS.rightW);
  const agentH = partial.agentH ?? readCssPx('--right-agent-h', SIZE_DEFAULTS.agentH);
  root.style.setProperty('--sidebar-w', `${sidebarW}px`);
  root.style.setProperty('--right-w', `${rightW}px`);
  root.style.setProperty('--right-agent-h', `${agentH}px`);
}

export function readLayoutSizesFromCss(): Pick<LayoutPersist, 'sidebarW' | 'rightW' | 'agentH'> {
  return {
    sidebarW: readCssPx('--sidebar-w', SIZE_DEFAULTS.sidebarW),
    rightW: readCssPx('--right-w', SIZE_DEFAULTS.rightW),
    agentH: readCssPx('--right-agent-h', SIZE_DEFAULTS.agentH),
  };
}
