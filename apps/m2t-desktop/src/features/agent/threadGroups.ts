import type { ThreadRow } from './types';

export type ThreadTimeGroup = 'today' | 'yesterday' | 'week' | 'month';

export const THREAD_GROUP_LABELS: Record<ThreadTimeGroup, string> = {
  today: 'TODAY',
  yesterday: 'YESTERDAY',
  week: 'LAST 7 DAYS',
  month: 'LAST 30 DAYS',
};

export type GroupedThread = ThreadRow & { group: ThreadTimeGroup };

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export function groupThreadByUpdatedAt(updatedAt: string | null | undefined): ThreadTimeGroup {
  if (!updatedAt) return 'month';
  const ts = Date.parse(updatedAt);
  if (Number.isNaN(ts)) return 'month';
  const updated = new Date(ts);
  const now = new Date();
  const today = startOfDay(now).getTime();
  const updatedDay = startOfDay(updated).getTime();
  const dayDiff = Math.floor((today - updatedDay) / 86400000);
  if (dayDiff <= 0) return 'today';
  if (dayDiff === 1) return 'yesterday';
  if (dayDiff <= 7) return 'week';
  if (dayDiff <= 30) return 'month';
  return 'month';
}

export function groupThreads(threads: ThreadRow[]): GroupedThread[] {
  return threads.map((t) => ({
    ...t,
    group: groupThreadByUpdatedAt(t.updated_at),
  }));
}

export function filterThreadsByQuery(threads: GroupedThread[], query: string): GroupedThread[] {
  const q = query.trim().toLowerCase();
  if (!q) return threads;
  return threads.filter((t) => (t.title || '').toLowerCase().includes(q));
}
