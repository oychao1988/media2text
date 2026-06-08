import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiGet } from '../../lib/api';
import type { LiveSessionSummary } from '../../lib/types';
import {
  expandSessionToMentionRows,
  filterMentionRows,
  type MentionDocumentRow,
} from './mentionDocuments';

const CACHE_TTL_MS = 5 * 60 * 1000;
const MAX_CONCURRENT = 3;

type CreatorRef = { id: string; display_name: string | null };

type CacheEntry = {
  fetchedAt: number;
  sessions: LiveSessionSummary[];
};

export function useMentionSessionIndex(creators: CreatorRef[], query: string, open: boolean) {
  const cacheRef = useRef(new Map<string, CacheEntry>());
  const [sessionsByCreator, setSessionsByCreator] = useState<
    Record<string, LiveSessionSummary[]>
  >({});
  const [loading, setLoading] = useState(false);
  const inflightRef = useRef(0);
  const queueRef = useRef<string[]>([]);

  const matchedCreatorIds = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return creators.map((c) => c.id);
    return creators
      .filter((c) => {
        const name = (c.display_name ?? c.id).toLowerCase();
        return name.includes(q);
      })
      .map((c) => c.id);
  }, [creators, query]);

  const creatorNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const c of creators) {
      map.set(c.id, c.display_name ?? c.id);
    }
    return map;
  }, [creators]);

  const fetchCreator = useCallback(async (creatorId: string) => {
    const cached = cacheRef.current.get(creatorId);
    const now = Date.now();
    if (cached && now - cached.fetchedAt < CACHE_TTL_MS) {
      setSessionsByCreator((prev) => ({ ...prev, [creatorId]: cached.sessions }));
      return;
    }
    const res = await apiGet<{ ok: boolean; sessions: LiveSessionSummary[] }>(
      `/api/creators/${creatorId}/sessions?limit=100`,
      true,
    );
    const sessions = (res.sessions ?? []).filter(
      (s) => s.has_transcript || s.has_summary,
    );
    cacheRef.current.set(creatorId, { fetchedAt: now, sessions });
    setSessionsByCreator((prev) => ({ ...prev, [creatorId]: sessions }));
  }, []);

  const pumpQueue = useCallback(async () => {
    while (inflightRef.current < MAX_CONCURRENT && queueRef.current.length > 0) {
      const creatorId = queueRef.current.shift();
      if (!creatorId) break;
      inflightRef.current += 1;
      try {
        await fetchCreator(creatorId);
      } catch {
        /* ignore per-creator failure */
      } finally {
        inflightRef.current -= 1;
        void pumpQueue();
      }
    }
    if (inflightRef.current === 0 && queueRef.current.length === 0) {
      setLoading(false);
    }
  }, [fetchCreator]);

  useEffect(() => {
    if (!open) return;
    const needed = matchedCreatorIds.filter((id) => {
      const cached = cacheRef.current.get(id);
      return !cached || Date.now() - cached.fetchedAt >= CACHE_TTL_MS;
    });
    if (needed.length === 0) {
      setLoading(false);
      return;
    }
    setLoading(true);
    queueRef.current = [...new Set([...queueRef.current, ...needed])];
    void pumpQueue();
  }, [open, matchedCreatorIds, pumpQueue]);

  const rows = useMemo((): MentionDocumentRow[] => {
    const ids = query.trim() ? matchedCreatorIds : creators.map((c) => c.id);
    const out: MentionDocumentRow[] = [];
    for (const id of ids) {
      const sessions = sessionsByCreator[id] ?? cacheRef.current.get(id)?.sessions ?? [];
      const name = creatorNameById.get(id) ?? id;
      for (const session of sessions) {
        out.push(...expandSessionToMentionRows(session, name));
      }
    }
    return filterMentionRows(out, query);
  }, [creators, creatorNameById, matchedCreatorIds, query, sessionsByCreator]);

  return { rows, loading };
}
