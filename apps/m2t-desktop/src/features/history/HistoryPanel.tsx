import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ApiError, apiDelete, apiPost, getApiBaseUrl } from '../../lib/api';
import { showToast } from '../../lib/toast';
import type { LiveGroup, LiveSessionSummary } from '../../lib/types';
import {
  cancelPendingHistoryEnrich,
  fetchHistory,
  invalidateHistoryCache,
  readHistoryCache,
  scheduleHistoryEnrich,
  type HistoryFilter,
} from './historyCache';
import {
  formatSessionDuration,
  historyKindLabel,
  historyRowTitle,
  sessionCanDeleteLocal,
  sessionCanDownloadCloud,
  sessionCanRetryVodDownload,
  sessionCloudLabel,
  sessionIsDisabled,
  sessionLocalLabel,
  sessionStatusTag,
} from './sessionDisplay';

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

function SessionTags({
  session,
  detailsPending,
}: {
  session: LiveSessionSummary;
  detailsPending?: boolean;
}) {
  const duration = formatSessionDuration(session.started_at, session.ended_at);
  const statusTag = sessionStatusTag(session);
  const local = sessionLocalLabel(session, { pending: detailsPending });
  const cloud = sessionCloudLabel(session, {
    pending:
      detailsPending && session.cloud_upload_status == null && !session.cloud_available,
  });

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

export function HistoryPanel({ creatorId, active, onSessionSelect }: Props) {
  const requestRef = useRef(0);
  const listAbortRef = useRef<AbortController | null>(null);
  const [sessions, setSessions] = useState<LiveSessionSummary[]>([]);
  const [groups, setGroups] = useState<LiveGroup[]>([]);
  const [filter, setFilter] = useState<HistoryFilter>('all');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);

  useEffect(() => {
    if (creatorId) void getApiBaseUrl();
  }, [creatorId]);

  const reload = useCallback(
    async (id: string, nextFilter: HistoryFilter, opts?: { background?: boolean }) => {
      const reqId = ++requestRef.current;
      listAbortRef.current?.abort();
      const listAbort = new AbortController();
      listAbortRef.current = listAbort;

      const cached = readHistoryCache(id, nextFilter);
      if (cached) {
        setSessions(cached.sessions);
        setGroups(cached.groups);
        setLoading(false);
        setDetailsLoading(!cached.enriched);
      } else if (!opts?.background) {
        setSessions([]);
        setGroups([]);
        setLoading(true);
        setDetailsLoading(false);
      }

      try {
        const entry = await fetchHistory(id, nextFilter, listAbort.signal);
        if (reqId !== requestRef.current) return;
        setSessions(entry.sessions);
        setGroups(entry.groups);
        setLoading(false);

        const cachedAfter = readHistoryCache(id, nextFilter);
        if (cachedAfter?.enriched) {
          setSessions(cachedAfter.sessions);
          setDetailsLoading(false);
          return;
        }

        if (!entry.sessions.length) {
          setDetailsLoading(false);
          return;
        }

        setDetailsLoading(true);
        scheduleHistoryEnrich(id, nextFilter, entry.sessions, {
          isStale: () => reqId !== requestRef.current,
          onComplete: (enriched) => {
            if (reqId !== requestRef.current) return;
            setSessions(enriched);
            setDetailsLoading(false);
          },
        });
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return;
        if (reqId !== requestRef.current) return;
        if (!readHistoryCache(id, nextFilter)) {
          setSessions([]);
          setGroups([]);
        }
        setDetailsLoading(false);
      } finally {
        if (reqId === requestRef.current) {
          setLoading(false);
        }
      }
    },
    [],
  );

  useEffect(() => {
    if (!creatorId) {
      requestRef.current += 1;
      listAbortRef.current?.abort();
      cancelPendingHistoryEnrich();
      setSessions([]);
      setGroups([]);
      setLoading(false);
      setDetailsLoading(false);
      return;
    }
    if (!active) return;
    void reload(creatorId, filter);
    return () => {
      cancelPendingHistoryEnrich();
    };
  }, [active, creatorId, filter, reload]);

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

  const retryVodDownload = async (session: LiveSessionSummary) => {
    if (!creatorId || !sessionCanRetryVodDownload(session)) return;
    const rowKey = `${session.kind}:${session.item_id}`;
    setBusyKey(rowKey);
    try {
      await apiPost(`/api/creators/${creatorId}/history/vod/${session.item_id}/retry-download`);
      showToast('已加入下载队列', 'success');
      invalidateHistoryCache(creatorId);
      await reload(creatorId, filter, { background: true });
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : '重试下载失败';
      showToast(msg, 'error');
    } finally {
      setBusyKey(null);
    }
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
      invalidateHistoryCache(creatorId);
      await reload(creatorId, filter, { background: true });
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

      <div className="history-list" id="history-list">
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
                      <SessionTags session={s} detailsPending={detailsLoading} />
                    </div>
                  </div>
                  <div
                    className="session-actions"
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => e.stopPropagation()}
                  >
                    {sessionCanRetryVodDownload(s) ? (
                      <button
                        type="button"
                        className="btn btn-sm session-action"
                        disabled={busy}
                        title="重新加入下载队列"
                        onClick={() => void retryVodDownload(s)}
                      >
                        重试
                      </button>
                    ) : null}
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
