import { useEffect, useMemo, useState } from 'react';
import { apiGet } from '../../lib/api';
import type { LiveGroup, LiveSessionSummary } from '../../lib/types';
import { ViewPlayback } from './ViewPlayback';

type Filter = 'all' | 'transcript' | 'summary';

type Props = {
  creatorId: string | null;
  active?: boolean;
  onSessionSelect?: (session: LiveSessionSummary | null) => void;
};

function formatSessionTime(start: string | null, end: string | null): string {
  const fmt = (iso: string | null) => {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
    } catch {
      return iso;
    }
  };
  return `${fmt(start)} – ${fmt(end)}`;
}

function groupByDate(sessions: LiveSessionSummary[]): Map<string, LiveSessionSummary[]> {
  const map = new Map<string, LiveSessionSummary[]>();
  for (const s of sessions) {
    const day = s.started_at?.slice(0, 10) ?? '未知';
    const arr = map.get(day) ?? [];
    arr.push(s);
    map.set(day, arr);
  }
  return map;
}

export function HistoryPanel({ creatorId, active, onSessionSelect }: Props) {
  const [sessions, setSessions] = useState<LiveSessionSummary[]>([]);
  const [groups, setGroups] = useState<LiveGroup[]>([]);
  const [filter, setFilter] = useState<Filter>('all');
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!creatorId) {
      setSessions([]);
      setGroups([]);
      setSelectedId(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const params = new URLSearchParams();
        if (filter === 'transcript') params.set('has_transcript', 'true');
        if (filter === 'summary') params.set('has_summary', 'true');
        const q = params.toString();
        const res = await apiGet<{
          ok: boolean;
          sessions: LiveSessionSummary[];
          live_groups: LiveGroup[];
        }>(`/api/creators/${creatorId}/sessions${q ? `?${q}` : ''}`, true);
        if (cancelled) return;
        setSessions(res.sessions ?? []);
        setGroups(res.live_groups ?? []);
        setSelectedId((prev) => {
          if (prev && res.sessions.some((s) => s.session_id === prev)) return prev;
          return res.sessions[0]?.session_id ?? null;
        });
      } catch {
        if (!cancelled) {
          setSessions([]);
          setGroups([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [creatorId, filter]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => {
      const day = s.started_at?.slice(0, 10) ?? '';
      return day.includes(q) || s.session_id.includes(q);
    });
  }, [sessions, search]);

  const byDate = useMemo(() => groupByDate(filtered), [filtered]);
  const selected = sessions.find((s) => s.session_id === selectedId) ?? null;

  useEffect(() => {
    onSessionSelect?.(selected);
  }, [selected, onSessionSelect]);

  return (
    <div className={`center-view${active ? ' active' : ''}`} id="view-history">
      <div className="history-toolbar">
        <button
          className={`chip${filter === 'all' ? ' active' : ''}`}
          type="button"
          data-filter="all"
          onClick={() => setFilter('all')}
        >
          全部
        </button>
        <button
          className={`chip${filter === 'transcript' ? ' active' : ''}`}
          type="button"
          data-filter="transcript"
          onClick={() => setFilter('transcript')}
        >
          仅有转写
        </button>
        <button
          className={`chip${filter === 'summary' ? ' active' : ''}`}
          type="button"
          data-filter="summary"
          onClick={() => setFilter('summary')}
        >
          仅有摘要
        </button>
        <input
          className="history-search"
          type="search"
          id="history-search"
          placeholder="搜索日期…"
          aria-label="搜索历史场次"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="history-layout">
        <div className="history-list" id="history-list">
          {loading ? <p className="hint">加载历史…</p> : null}
          {!loading && !filtered.length ? (
            <p className="hint">暂无匹配场次</p>
          ) : null}
          {[...byDate.entries()].map(([day, rows]) => (
            <div className="history-group" key={day}>
              <div className="history-group-title">{day}</div>
              {rows.map((s) => (
                <div
                  key={s.session_id}
                  className={`session-row${selectedId === s.session_id ? ' selected' : ''}`}
                  tabIndex={0}
                  role="button"
                  onClick={() => setSelectedId(s.session_id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelectedId(s.session_id);
                    }
                  }}
                >
                  <div className="dot-col">
                    <span className="dot" />
                  </div>
                  <div className="session-main">
                    <div className="session-time">{formatSessionTime(s.started_at, s.ended_at)}</div>
                    <div className="session-meta">
                      <span>{s.status ?? '—'}</span>
                      {s.has_transcript ? <span className="tag ok">转写</span> : null}
                      {s.has_summary ? <span className="tag ok">摘要</span> : null}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ))}
          {groups.length ? (
            <div className="history-group">
              <div className="history-group-title">合并组</div>
              {groups.map((g, i) => (
                <div className="session-row merged" key={`${g.date}-${i}`}>
                  <div className="session-main">
                    <div className="session-time">{g.date ?? g.label ?? '合并直播'}</div>
                    <div className="session-meta">
                      <span>{(g.session_ids ?? []).length} 段</span>
                      {g.summary_path ? <span className="tag ok">merged</span> : null}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        <ViewPlayback mediaPath={selected?.media_path ?? selected?.local_path ?? selected?.temp_path ?? null} />
      </div>
    </div>
  );
}
