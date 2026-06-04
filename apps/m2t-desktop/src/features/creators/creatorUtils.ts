import type { StatusLight } from '../../lib/types';

const ARIA_BY_LIGHT: Record<StatusLight, string> = {
  green: '录制中',
  red: '在播未录',
  yellow: '收尾中',
  gray: '离线',
};

export function statusAriaLabel(light: StatusLight): string {
  return ARIA_BY_LIGHT[light];
}

/** Manage list row status line (matches finalized.html). */
export function manageStatusText(c: {
  monitor_enabled: boolean;
  status_light: StatusLight;
}): string {
  if (!c.monitor_enabled) return '未监控';
  return statusAriaLabel(c.status_light);
}

export function creatorInitial(name: string | null | undefined): string {
  const n = (name ?? '').trim();
  if (!n) return '?';
  return n.charAt(0);
}

export function formatCreatorSub(c: {
  platform: string;
  status_light: StatusLight;
  is_live: boolean;
}): string {
  const platform = c.platform;
  if (c.status_light === 'green') return `${platform} · 录制中`;
  if (c.status_light === 'yellow') return `${platform} · 收尾中`;
  if (c.is_live || c.status_light === 'red') return `${platform} · 直播中`;
  return `${platform} · 离线`;
}

export function autoRecordPillLabel(
  monitorEnabled: boolean,
  override: 'inherit' | 'on' | 'off',
): { text: string; className: string } {
  if (!monitorEnabled) return { text: '—', className: 'manage-auto-pill tag-pill' };
  if (override === 'on') return { text: '自动', className: 'manage-auto-pill tag-pill accent' };
  if (override === 'off') return { text: '手动', className: 'manage-auto-pill tag-pill' };
  return { text: '继承', className: 'manage-auto-pill tag-pill' };
}

export function showFlvBadge(): boolean {
  if (import.meta.env.DEV) return true;
  try {
    return new URLSearchParams(window.location.search).has('debug');
  } catch {
    return false;
  }
}
