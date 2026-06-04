import { useEffect, useMemo, useRef, useState } from 'react';
import { apiGet } from '../../lib/api';
import type { LiveGroup, LiveSessionSummary } from '../../lib/types';
import {
  formatSessionDuration,
  formatSessionTime,
  sessionIsDisabled,
  sessionSizeLabel,
} from './sessionDisplay';

type Filter = 'all' | 'transcript' | 'summary';

type Props = {
  creatorId: string | null;
  active?: boolean;
  onSessionSelect?: (session: LiveSessionSummary) => void;
};

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

function SessionTags({ session }: { session: LiveSessionSummary }) {
  const duration = formatSessionDuration(session.started_at, session.ended_at);
  const status = session.status ?? '—';
  const statusClass =
    status === 'failed' ? 'fail' : status === 'completed' || status === 'done' ? 'ok' : '';

  return (
    <>
      {duration ? <span>{duration}</span> : null}
      {statusClass ? <span className={`tag ${statusClass}`}>{status}</span> : <span>{status}</span>}
      {session.has_transcript ? (
        <span className="tag ok">✓ 转写</span>
      ) : (
        <span className="tag miss">无转写</span>
      )}
      {session.has_summary ? (
        <span className="tag ok">✓ 摘要</span>
      ) : (
        <span className="tag miss">无摘要</span>
      )}
      {session.pipeline_mode === 'streaming' ? <span className="tag">streaming</span> : null}
      {session.cloud_upload_status === 'uploaded' && !session.local_path ? (
        <span className="tag cloud">☁ 仅云端</span>
      ) : null}
    </>
  );
}

type HistoryCacheEntry = {
  sessions: LiveSessionSummary[];
  groups: LiveGroup[];
};

function historyCacheKey(creatorId: string, filter: Filter) {
  return `${creatorId}:${filter}`;
}

export function HistoryPanel({ creatorId, active, onSessionSelect }: Props) {
  const cacheRef = useRef(new Map<string, HistoryCacheEntry>());
  const [sessions, setSessions] = useState<LiveSessionSummary[]>([]);
  const [groups, setGroups] = useState<LiveGroup[]>([]);
  const [filter, setFilter] = useState<Filter>('all');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    if (!creatorId) {
      setSessions([]);
      setGroups([]);
      setLoading(false);
      setRefreshing(false);
      return;
    }

    const key = historyCacheKey(creatorId, filter);
    const cached = cacheRef.current.get(key);
    if (cached) {
      setSessions(cached.sessions);
      setGroups(cached.groups);
      setLoading(false);
      setRefreshing(true);
    } else {
      setSessions([]);
      setGroups([]);
      setLoading(true);
      setRefreshing(false);
    }

    let cancelled = false;
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
        const entry: HistoryCacheEntry = {
          sessions: res.sessions ?? [],
          groups: res.live_groups ?? [],
        };
        cacheRef.current.set(key, entry);
        setSessions(entry.sessions);
        setGroups(entry.groups);
      } catch {
        if (!cancelled && !cached) {
          setSessions([]);
          setGroups([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          setRefreshing(false);
        }
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

  const openSession = (session: LiveSessionSummary) => {
    if (sessionIsDisabled(session)) return;
    onSessionSelect?.(session);
  };

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

      <div className={`history-list${refreshing ? ' is-refreshing' : ''}`} id="history-list">
        {loading ? <p className="hint">加载历史…</p> : null}
        {!loading && !filtered.length ? <p className="hint">暂无匹配场次</p> : null}
        {[...byDate.entries()].map(([day, rows]) => (
          <div className="history-group" key={day}>
            <div className="history-group-title">{day}</div>
            {rows.map((s) => {
              const disabled = sessionIsDisabled(s);
              return (
                <div
                  key={s.session_id}
                  className={`session-row${disabled ? ' disabled' : ''}`}
                  tabIndex={disabled ? -1 : 0}
                  role="button"
                  title={disabled ? '录制失败，无媒体文件' : undefined}
                  onClick={() => openSession(s)}
                  onKeyDown={(e) => {
                    if (disabled) return;
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      openSession(s);
                    }
                  }}
                >
                  <div className="dot-col">
                    <span className="dot" />
                  </div>
                  <div className="session-main">
                    <div className="session-time">
                      {formatSessionTime(s.started_at, s.ended_at)}
                    </div>
                    <div className="session-meta">
                      <SessionTags session={s} />
                    </div>
                  </div>
                  <div className="session-size">{sessionSizeLabel(s)}</div>
                </div>
              );
            })}
          </div>
        ))}
        {groups.length ? (
          <div className="history-group">
            <div className="history-group-title">
              合并组
              {groups.length ? (
                <span className="merge-badge">
                  合并组 · {groups.reduce((n, g) => n + (g.session_ids?.length ?? 0), 0)} 段
                </span>
              ) : null}
            </div>
            {groups.map((g, i) => (
              <div
                className="merged-row"
                key={`${g.date}-${i}`}
                id={i === 0 ? 'merged-row' : undefined}
                role={i === 0 ? 'button' : 'group'}
                tabIndex={i === 0 ? 0 : undefined}
              >
                <div>
                  <strong>{g.summary_path?.split('/').pop() ?? g.label ?? '合并直播'}</strong>
                  <span>
                    {' '}
                    · {(g.session_ids ?? []).length} 段
                    {g.date ? ` · ${g.date}` : ''}
                  </span>
                </div>
                {g.summary_path ? (
                  <button type="button" className="btn btn-sm" id="btn-open-merged">
                    打开摘要
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
