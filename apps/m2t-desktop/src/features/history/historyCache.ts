import { apiGet } from '../../lib/api';
import type { LiveGroup, LiveSessionSummary } from '../../lib/types';
import { mergeSessionEnrichInfo, sessionCloudKey, type SessionEnrichFields } from './historyCloud';

export type HistoryFilter = 'all' | 'transcript' | 'summary';

export type HistoryCacheEntry = {
  sessions: LiveSessionSummary[];
  groups: LiveGroup[];
  enriched?: boolean;
};

const globalHistoryCache = new Map<string, HistoryCacheEntry>();
const inflightList = new Map<string, Promise<HistoryCacheEntry | null>>();
const inflightEnrich = new Map<string, Promise<LiveSessionSummary[]>>();

let activeEnrichController: AbortController | null = null;
let enrichDebounceTimer: ReturnType<typeof setTimeout> | null = null;

function isAbortError(err: unknown): boolean {
  return err instanceof Error && err.name === 'AbortError';
}

export function historyCacheKey(creatorId: string, filter: HistoryFilter): string {
  return `${creatorId}:${filter}`;
}

export function readHistoryCache(creatorId: string, filter: HistoryFilter): HistoryCacheEntry | null {
  return globalHistoryCache.get(historyCacheKey(creatorId, filter)) ?? null;
}

/** Cancel debounced / in-flight enrich when switching creators. */
export function cancelPendingHistoryEnrich(): void {
  activeEnrichController?.abort();
  activeEnrichController = null;
  if (enrichDebounceTimer) {
    clearTimeout(enrichDebounceTimer);
    enrichDebounceTimer = null;
  }
}

export function invalidateHistoryCache(creatorId: string): void {
  for (const key of [...globalHistoryCache.keys()]) {
    if (key.startsWith(`${creatorId}:`)) {
      globalHistoryCache.delete(key);
      inflightList.delete(key);
      inflightEnrich.delete(key);
    }
  }
}

async function fetchHistoryList(
  creatorId: string,
  filter: HistoryFilter,
  signal?: AbortSignal,
): Promise<HistoryCacheEntry> {
  const params = new URLSearchParams({ include_cloud: 'false' });
  if (filter === 'transcript') params.set('has_transcript', 'true');
  if (filter === 'summary') params.set('has_summary', 'true');
  const res = await apiGet<{
    ok: boolean;
    sessions: LiveSessionSummary[];
    live_groups: LiveGroup[];
  }>(`/api/creators/${creatorId}/sessions?${params.toString()}`, true, signal);
  return {
    sessions: res.sessions ?? [],
    groups: res.live_groups ?? [],
  };
}

async function fetchHistoryEnrich(
  creatorId: string,
  sessions: LiveSessionSummary[],
  signal?: AbortSignal,
): Promise<Record<string, SessionEnrichFields>> {
  if (!sessions.length) return {};
  const keys = sessions.map((s) => sessionCloudKey(s)).join(',');
  const res = await apiGet<{ ok: boolean; items: Record<string, SessionEnrichFields> }>(
    `/api/creators/${creatorId}/sessions/cloud?keys=${encodeURIComponent(keys)}`,
    true,
    signal,
  );
  return res.items ?? {};
}

export async function fetchHistory(
  creatorId: string,
  filter: HistoryFilter = 'all',
  signal?: AbortSignal,
): Promise<HistoryCacheEntry> {
  const key = historyCacheKey(creatorId, filter);
  const cached = globalHistoryCache.get(key);
  if (cached) return cached;

  const pending = inflightList.get(key);
  if (pending) {
    const hit = await pending;
    if (hit) return hit;
  }

  const task = (async () => {
    const entry = await fetchHistoryList(creatorId, filter, signal);
    globalHistoryCache.set(key, entry);
    return entry;
  })();

  inflightList.set(
    key,
    task.then((entry) => entry).catch((err) => {
      if (isAbortError(err)) throw err;
      return null;
    }),
  );
  try {
    return await task;
  } finally {
    inflightList.delete(key);
  }
}

async function runHistoryEnrich(
  creatorId: string,
  filter: HistoryFilter,
  sessions: LiveSessionSummary[],
  signal: AbortSignal,
): Promise<LiveSessionSummary[]> {
  const key = historyCacheKey(creatorId, filter);
  const cached = globalHistoryCache.get(key);
  if (cached?.enriched) return cached.sessions;

  const pending = inflightEnrich.get(key);
  if (pending) return pending;

  const task = (async () => {
    const items = await fetchHistoryEnrich(creatorId, sessions, signal);
    const merged = mergeSessionEnrichInfo(sessions, items);
    const current = globalHistoryCache.get(key);
    if (current) {
      globalHistoryCache.set(key, { ...current, sessions: merged, enriched: true });
    }
    return merged;
  })();

  inflightEnrich.set(key, task);
  try {
    return await task;
  } finally {
    inflightEnrich.delete(key);
  }
}

/**
 * Enrich only after the user stops switching creators (debounce).
 * Aborts any previous enrich when called again.
 */
export function scheduleHistoryEnrich(
  creatorId: string,
  filter: HistoryFilter,
  sessions: LiveSessionSummary[],
  opts?: {
    debounceMs?: number;
    isStale?: () => boolean;
    onComplete?: (sessions: LiveSessionSummary[]) => void;
  },
): void {
  cancelPendingHistoryEnrich();
  if (!sessions.length) return;

  const debounceMs = opts?.debounceMs ?? 350;
  enrichDebounceTimer = setTimeout(() => {
    enrichDebounceTimer = null;
    if (opts?.isStale?.()) return;

    const key = historyCacheKey(creatorId, filter);
    const cached = globalHistoryCache.get(key);
    if (cached?.enriched) {
      opts?.onComplete?.(cached.sessions);
      return;
    }

    activeEnrichController = new AbortController();
    const { signal } = activeEnrichController;
    void runHistoryEnrich(creatorId, filter, sessions, signal)
      .then((merged) => {
        if (opts?.isStale?.()) return;
        opts?.onComplete?.(merged);
      })
      .catch((err) => {
        if (isAbortError(err)) return;
      })
      .finally(() => {
        if (activeEnrichController?.signal === signal) {
          activeEnrichController = null;
        }
      });
  }, debounceMs);
}

/** @deprecated use scheduleHistoryEnrich from HistoryPanel */
export async function ensureHistoryEnriched(
  creatorId: string,
  filter: HistoryFilter,
  sessions: LiveSessionSummary[],
): Promise<LiveSessionSummary[]> {
  cancelPendingHistoryEnrich();
  activeEnrichController = new AbortController();
  try {
    return await runHistoryEnrich(
      creatorId,
      filter,
      sessions,
      activeEnrichController.signal,
    );
  } finally {
    activeEnrichController = null;
  }
}

export const prefetchHistory = fetchHistory;

export async function loadHistoryEnrich(
  creatorId: string,
  sessions: LiveSessionSummary[],
  cacheKey: string,
): Promise<LiveSessionSummary[]> {
  const filter = cacheKey.split(':').slice(1).join(':') as HistoryFilter;
  return ensureHistoryEnriched(creatorId, filter, sessions);
}
