import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { apiDelete, apiGet, apiPost } from '../../lib/api';
import { showToast } from '../../lib/toast';
import type { LiveGroup, LiveSessionSummary } from '../../lib/types';
import {
  formatSessionDuration,
  historyKindLabel,
  historyRowTitle,
  sessionCanDeleteLocal,
  sessionCanDownloadCloud,
  sessionCloudLabel,
  sessionIsDisabled,
  sessionLocalLabel,
  sessionStatusTag,
} from './sessionDisplay';

type Filter = 'all' | 'transcript' | 'summary';

type Props = {
  creatorId: string | null;
  active?: boolean;
  onSessionSelect?: (session: LiveSessionSummary) => void;
};

type PendingAction =
  | { type: 'delete-local'; session: LiveSessionSummary }
  | { type: 'download-cloud'; session: LiveSessionSummary }
  | { type: 'delete-record'; session: LiveSessionSummary };

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
  const statusTag = sessionStatusTag(session);
  const local = sessionLocalLabel(session);
  const cloud = sessionCloudLabel(session);

  return (
    <>
      <span className="tag kind">{historyKindLabel(session)}</span>
      {duration ? <span>{duration}</span> : null}
      {statusTag ? <span className={`tag ${statusTag.className}`}>{statusTag.text}</span> : null}
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
      <span className={`tag ${local.className}`}>{local.text}</span>
      <span className={`tag ${cloud.className}`}>{cloud.text}</span>
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
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);

  const invalidateCache = useCallback(() => {
    if (!creatorId) return;
    for (const key of [...cacheRef.current.keys()]) {
      if (key.startsWith(`${creatorId}:`)) cacheRef.current.delete(key);
    }
  }, [creatorId]);

  const loadSessions = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!creatorId) return;
      const key = historyCacheKey(creatorId, filter);
      if (!opts?.silent) {
        const cached = cacheRef.current.get(key);
        if (cached) {
          setSessions(cached.sessions);
          setGroups(cached.groups);
          setLoading(false);
          setRefreshing(true);
        } else {
          setLoading(true);
          setRefreshing(false);
        }
      }

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
        const entry: HistoryCacheEntry = {
          sessions: res.sessions ?? [],
          groups: res.live_groups ?? [],
        };
        cacheRef.current.set(key, entry);
        setSessions(entry.sessions);
        setGroups(entry.groups);
      } catch {
        if (!opts?.silent && !cacheRef.current.get(key)) {
          setSessions([]);
          setGroups([]);
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [creatorId, filter],
  );

  useEffect(() => {
    if (!creatorId) {
      setSessions([]);
      setGroups([]);
      setLoading(false);
      setRefreshing(false);
      return;
    }
    void loadSessions();
  }, [creatorId, loadSessions]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => {
      const day = s.started_at?.slice(0, 10) ?? '';
      const title = s.title?.toLowerCase() ?? '';
      return day.includes(q) || title.includes(q) || s.item_id.includes(q);
    });
  }, [sessions, search]);

  const byDate = useMemo(() => groupByDate(filtered), [filtered]);

  const openSession = (session: LiveSessionSummary) => {
    if (sessionIsDisabled(session)) return;
    onSessionSelect?.(session);
  };

  const runAction = async (action: PendingAction) => {
    if (!creatorId) return;
    const { session } = action;
    const rowKey = `${session.kind}:${session.item_id}`;
    setBusyKey(rowKey);
    try {
      if (action.type === 'delete-local') {
        await apiPost(
          `/api/creators/${creatorId}/history/${session.kind}/${session.item_id}/delete-local`,
        );
        showToast('已删除本地视频', 'success');
      } else if (action.type === 'download-cloud') {
        await apiPost(
          `/api/creators/${creatorId}/history/${session.kind}/${session.item_id}/download-cloud`,
        );
        showToast('已从云端下载到本地', 'success');
      } else {
        await apiDelete(`/api/creators/${creatorId}/history/${session.kind}/${session.item_id}`);
        showToast('已删除记录', 'success');
      }
      invalidateCache();
      await loadSessions({ silent: true });
    } catch {
      /* toast handled by api */
    } finally {
      setBusyKey(null);
      setPendingAction(null);
    }
  };

  const confirmCopy = pendingAction
    ? {
        'delete-local': {
          title: '删除本地视频',
          message: '仅删除本地媒体文件，云端备份与转写/摘要 sidecar 保留。确定继续？',
          confirmLabel: '删除本地',
          danger: true,
        },
        'download-cloud': {
          title: '从云端下载',
          message: '将云盘中的视频下载到本地工作区，便于回放。确定继续？',
          confirmLabel: '下载',
          danger: false,
        },
        'delete-record': {
          title: '删除记录',
          message: '删除数据库记录及本地媒体与 sidecar，云端文件不受影响。确定继续？',
          confirmLabel: '删除记录',
          danger: true,
        },
      }[pendingAction.type]
    : null;

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
          placeholder="搜索日期或标题…"
          aria-label="搜索历史"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className={`history-list${refreshing ? ' is-refreshing' : ''}`} id="history-list">
        {loading ? <p className="hint">加载历史…</p> : null}
        {!loading && !filtered.length ? <p className="hint">暂无匹配记录</p> : null}
        {[...byDate.entries()].map(([day, rows]) => (
          <div className="history-group" key={day}>
            <div className="history-group-title">{day}</div>
            {rows.map((s) => {
              const disabled = sessionIsDisabled(s);
              const rowKey = `${s.kind}:${s.item_id}`;
              const busy = busyKey === rowKey;
              return (
                <div
                  key={rowKey}
                  className={`session-row${disabled ? ' disabled' : ''}${busy ? ' is-busy' : ''}`}
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
                    <span className={`dot${s.kind === 'vod' ? ' dot-vod' : ''}`} />
                  </div>
                  <div className="session-main">
                    <div className="session-time">{historyRowTitle(s)}</div>
                    <div className="session-meta">
                      <SessionTags session={s} />
                    </div>
                  </div>
                  <div
                    className="session-actions"
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => e.stopPropagation()}
                  >
                    {sessionCanDownloadCloud(s) ? (
                      <button
                        type="button"
                        className="btn btn-sm session-action"
                        disabled={busy}
                        title="从云端下载"
                        onClick={() => setPendingAction({ type: 'download-cloud', session: s })}
                      >
                        下载
                      </button>
                    ) : null}
                    {sessionCanDeleteLocal(s) ? (
                      <button
                        type="button"
                        className="btn btn-sm session-action"
                        disabled={busy}
                        title="删除本地视频"
                        onClick={() => setPendingAction({ type: 'delete-local', session: s })}
                      >
                        删本地
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="btn btn-sm session-action session-action-danger"
                      disabled={busy}
                      title="删除记录"
                      onClick={() => setPendingAction({ type: 'delete-record', session: s })}
                    >
                      删除
                    </button>
                  </div>
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

      <ConfirmDialog
        open={pendingAction != null}
        title={confirmCopy?.title ?? ''}
        message={confirmCopy?.message ?? ''}
        confirmLabel={confirmCopy?.confirmLabel}
        danger={confirmCopy?.danger}
        onCancel={() => setPendingAction(null)}
        onConfirm={() => {
          if (pendingAction) void runAction(pendingAction);
        }}
      />
    </div>
  );
}
