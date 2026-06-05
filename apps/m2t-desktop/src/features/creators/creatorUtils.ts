import type { Creator, StatusLight } from '../../lib/types';

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

/** Higher = more urgent live presence (sidebar pin order). */
export function creatorLiveRank(c: Pick<Creator, 'is_live' | 'status_light'>): number {
  if (c.status_light === 'green') return 2;
  if (c.is_live || c.status_light === 'red') return 1;
  return 0;
}

export function isCreatorLive(c: Pick<Creator, 'is_live' | 'status_light'>): boolean {
  return creatorLiveRank(c) > 0;
}

/** Pin live creators to the top; preserve API order within each tier. */
export function sortCreatorsLiveFirst<T extends Pick<Creator, 'is_live' | 'status_light'>>(creators: T[]): T[] {
  return creators
    .map((creator, index) => ({ creator, index }))
    .sort((a, b) => {
      const rankDiff = creatorLiveRank(b.creator) - creatorLiveRank(a.creator);
      return rankDiff !== 0 ? rankDiff : a.index - b.index;
    })
    .map(({ creator }) => creator);
}

export function formatFollowerCount(count: number | null | undefined): string | null {
  if (count == null || count < 0) return null;
  if (count >= 100_000_000) {
    const v = count / 100_000_000;
    return `${v >= 10 ? Math.round(v) : v.toFixed(1).replace(/\.0$/, '')}亿`;
  }
  if (count >= 10_000) {
    const v = count / 10_000;
    return `${v >= 100 ? Math.round(v) : v.toFixed(1).replace(/\.0$/, '')}万`;
  }
  return count.toLocaleString('zh-CN');
}

export function formatProfileSyncedAt(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function hasSyncedProfile(c: {
  profile_synced_at?: string | null;
  avatar_url?: string | null;
  signature?: string | null;
  follower_count?: number | null;
}): boolean {
  return Boolean(
    c.profile_synced_at ||
      c.avatar_url ||
      c.signature ||
      (c.follower_count != null && c.follower_count >= 0),
  );
}

export function showFlvBadge(): boolean {
  if (import.meta.env.DEV) return true;
  try {
    return new URLSearchParams(window.location.search).has('debug');
  } catch {
    return false;
  }
}
