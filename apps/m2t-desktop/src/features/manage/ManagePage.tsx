import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { apiDelete, apiGet, apiPatch, apiPost } from '../../lib/api';
import { showToast } from '../../lib/toast';
import { openExternalUrl } from '../../lib/tauriBridge';
import type { ConfigDto, Creator } from '../../lib/types';
import { CreatorAvatar } from '../creators/CreatorAvatar';
import { CreatorProfileCard } from '../creators/CreatorProfileCard';
import { autoRecordPillLabel, manageStatusText } from '../creators/creatorUtils';
import { useCreators } from '../creators/CreatorsContext';

type ManageFilter = 'all' | 'on' | 'off';

type ManageDrawerProps = {
  creator: Creator;
  globalAutoRecord: boolean;
  syncBusy: string | null;
  onToggleMonitor: (c: Creator) => void;
  onToggleContentSync: (c: Creator) => void;
  onSetAutoRecord: (value: 'inherit' | 'on' | 'off') => void;
  onRunSync: (kind: 'profile' | 'catalog' | 'download' | 'dynamics') => void;
  onRemove: () => void;
};

function ManageCreatorDrawer({
  creator,
  globalAutoRecord,
  syncBusy,
  onToggleMonitor,
  onToggleContentSync,
  onSetAutoRecord,
  onRunSync,
  onRemove,
}: ManageDrawerProps) {
  const drawerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const drawer = drawerRef.current;
    if (!drawer?.scrollIntoView) return;
    drawer.scrollIntoView({ block: 'nearest', behavior: 'auto' });
  }, [creator.id]);

  return (
    <div
      ref={drawerRef}
      className="manage-drawer"
      id="manage-drawer"
      aria-label="博主详情抽屉"
      role="region"
      data-creator={creator.id}
    >
      <div className="manage-drawer-collapse">
        <div className="manage-drawer-inner">
          <div className="manage-drawer-toolbar">
            <h3 className="manage-drawer-title">博主设置</h3>
            <div className="manage-drawer-actions">
              {creator.profile_url ? (
                <button
                  type="button"
                  className="btn btn-sm"
                  id="detail-open-profile"
                  onClick={() => {
                    void openExternalUrl(creator.profile_url!).catch(() => {
                      showToast('无法打开主页', 'error');
                    });
                  }}
                >
                  打开主页
                </button>
              ) : null}
              <button
                type="button"
                className="btn-ghost btn-sm danger"
                id="detail-remove"
                onClick={onRemove}
              >
                移除博主
              </button>
            </div>
          </div>
          <CreatorProfileCard creator={creator} />
          <div className="inspector-grid">
            <section className="inspector-block">
              <h4>监控</h4>
              <div className="toggle-row">
                <span>直播检测 + 录制流水线</span>
                <button
                  type="button"
                  className={`toggle${creator.monitor_enabled ? ' on' : ''}`}
                  id="detail-monitor-toggle"
                  aria-pressed={creator.monitor_enabled}
                  aria-label="开启监控"
                  onClick={() => onToggleMonitor(creator)}
                />
              </div>
              <p className="hint">
                开启后由 daemon 自动处理；中栏「直播」预览可选，不影响后台录制。
              </p>
              <div className="toggle-row">
                <span>作品自动同步（投稿 / 动态）</span>
                <button
                  type="button"
                  className={`toggle${creator.content_sync_enabled ? ' on' : ''}`}
                  id="detail-content-sync-toggle"
                  aria-pressed={creator.content_sync_enabled}
                  aria-label="开启作品自动同步"
                  onClick={() => onToggleContentSync(creator)}
                />
              </div>
              <p className="hint">
                默认关闭。开启后 daemon 仅拉取最新投稿并自动下载；补历史请用下方「同步历史作品」。
              </p>
            </section>
            <section className="inspector-block" id="detail-auto-record-section">
              <h4>开录策略</h4>
              <div
                className="detail-record-segments radio-group"
                id="detail-auto-record-group"
                role="radiogroup"
                aria-label="开录策略"
              >
                {(
                  [
                    [
                      'inherit',
                      '继承全局',
                      `跟随全局设置（当前：${globalAutoRecord ? '开' : '关'}）`,
                    ],
                    ['on', '始终自动', '检测到直播即开录'],
                    ['off', '仅手动', '需在直播 Tab 点「开始录制」'],
                  ] as const
                ).map(([val, label, sub]) => (
                  <label
                    key={val}
                    className={`radio-opt${creator.auto_record_override === val ? ' selected' : ''}`}
                  >
                    <input
                      type="radio"
                      name="auto-record"
                      value={val}
                      checked={creator.auto_record_override === val}
                      onChange={() => onSetAutoRecord(val)}
                    />
                    <strong>{label}</strong>
                    <span>{sub}</span>
                  </label>
                ))}
              </div>
            </section>
            <section className="inspector-block ops">
              <h4>运维</h4>
              <p className="hint">
                自动同步只处理新投稿；「同步历史作品」会分页拉全量 catalog（较慢）。
              </p>
              <div className="detail-actions detail-actions--row">
                <button
                  type="button"
                  className="btn-ghost btn-sm"
                  id="detail-sync-profile"
                  disabled={syncBusy != null}
                  onClick={() => onRunSync('profile')}
                >
                  同步资料
                </button>
                <button
                  type="button"
                  className="btn btn-sm"
                  id="detail-sync-catalog"
                  disabled={syncBusy != null}
                  onClick={() => onRunSync('catalog')}
                >
                  同步历史作品
                </button>
                <button
                  type="button"
                  className="btn-ghost btn-sm"
                  id="detail-download-pending"
                  disabled={syncBusy != null}
                  onClick={() => onRunSync('download')}
                >
                  下载待发作品
                </button>
                {creator.platform === 'bilibili' ? (
                  <button
                    type="button"
                    className="btn-ghost btn-sm"
                    id="detail-sync-dynamics"
                    disabled={syncBusy != null}
                    onClick={() => onRunSync('dynamics')}
                  >
                    同步动态（B 站）
                  </button>
                ) : null}
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}

export function ManagePage() {
  const { refresh: refreshSidebar } = useCreators();
  const [creators, setCreators] = useState<Creator[]>([]);
  const [filter, setFilter] = useState<ManageFilter>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [syncBusy, setSyncBusy] = useState<string | null>(null);
  const [globalAutoRecord, setGlobalAutoRecord] = useState(true);
  const [removeTarget, setRemoveTarget] = useState<{ id: string; label: string } | null>(null);

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    try {
      const res = await apiGet<{ ok: boolean; creators: Creator[] }>('/api/creators?all=1', true);
      setCreators(res.creators ?? []);
      setSelectedId((prev) => {
        if (prev && res.creators.some((c) => c.id === prev)) return prev;
        return null;
      });
    } catch {
      if (!opts?.silent) setCreators([]);
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void apiGet<{ config: ConfigDto }>('/api/config', true)
      .then((res) => setGlobalAutoRecord(res.config.autoRecord))
      .catch(() => undefined);
  }, []);

  const filtered = useMemo(() => {
    if (filter === 'on') return creators.filter((c) => c.monitor_enabled);
    if (filter === 'off') return creators.filter((c) => !c.monitor_enabled);
    return creators;
  }, [creators, filter]);

  useEffect(() => {
    if (loading) return;
    if (!selectedId) return;
    if (filtered.some((c) => c.id === selectedId)) return;
    setSelectedId(null);
  }, [loading, filtered, selectedId]);

  const selected = creators.find((c) => c.id === selectedId) ?? null;
  const monitoredCount = creators.filter((c) => c.monitor_enabled).length;

  const selectCreator = (id: string) => {
    setSelectedId((prev) => (prev === id ? null : id));
  };

  const addCreator = async () => {
    const u = url.trim();
    if (!u) return;
    try {
      await apiPost('/api/creators', { url: u });
      showToast('博主已添加', 'success');
      setUrl('');
      await load();
      await refreshSidebar();
    } catch {
      /* toast */
    }
  };

  const patchCreator = async (
    id: string,
    body: Record<string, unknown>,
    optimistic?: Partial<Creator>,
  ) => {
    if (optimistic) {
      setCreators((prev) => prev.map((c) => (c.id === id ? { ...c, ...optimistic } : c)));
    }
    try {
      await apiPatch(`/api/creators/${id}`, body);
      await load({ silent: true });
      await refreshSidebar();
    } catch {
      await load({ silent: true });
      throw new Error('patch failed');
    }
  };

  const toggleMonitor = async (c: Creator) => {
    const next = !c.monitor_enabled;
    try {
      await patchCreator(c.id, { monitorEnabled: next }, { monitor_enabled: next });
      showToast(next ? '已开启监控' : '已关闭监控', 'success');
    } catch {
      /* toast */
    }
  };

  const toggleContentSync = async (c: Creator) => {
    const next = !c.content_sync_enabled;
    try {
      await patchCreator(
        c.id,
        { contentSyncEnabled: next },
        { content_sync_enabled: next },
      );
      showToast(next ? '已开启作品自动同步' : '已关闭作品自动同步', 'success');
    } catch {
      /* toast */
    }
  };

  const setAutoRecord = async (value: 'inherit' | 'on' | 'off') => {
    if (!selected) return;
    try {
      await patchCreator(selected.id, { autoRecordOverride: value }, {
        auto_record_override: value,
      });
    } catch {
      /* toast */
    }
  };

  const runSync = async (kind: 'profile' | 'catalog' | 'download' | 'dynamics') => {
    if (!selected) return;
    const key = `${selected.id}:${kind}`;
    setSyncBusy(key);
    try {
      if (kind === 'profile') {
        await apiPost(`/api/creators/${selected.id}/sync-profile`);
        showToast('资料同步完成', 'success');
      } else if (kind === 'catalog') {
        await apiPost(`/api/creators/${selected.id}/sync`);
        showToast('历史作品列表已同步', 'success');
      } else if (kind === 'download') {
        await apiPost(`/api/creators/${selected.id}/download`);
        showToast('已加入下载队列（需 daemon 运行）', 'success');
      } else {
        await apiPost(`/api/creators/${selected.id}/sync-dynamics`);
        showToast('动态同步完成', 'success');
      }
      await load({ silent: true });
      await refreshSidebar();
    } catch {
      showToast(kind === 'download' ? '加入下载队列失败' : '同步失败', 'error');
    } finally {
      setSyncBusy(null);
    }
  };

  const requestRemove = () => {
    if (!selected) return;
    setRemoveTarget({ id: selected.id, label: selected.display_name ?? selected.id });
  };

  const confirmRemove = async () => {
    if (!removeTarget) return;
    const { id } = removeTarget;
    setRemoveTarget(null);
    try {
      await apiDelete(`/api/creators/${id}`);
      showToast('已移除博主', 'success');
      setSelectedId(null);
      await load();
      await refreshSidebar();
    } catch {
      /* toast */
    }
  };

  return (
    <div className="center-view manage-page active" id="view-manage">
      <header className="manage-top">
        <div className="manage-top-left">
          <p className="manage-stats" id="manage-stats">
            已登记 <strong>{creators.length}</strong> · 监控中 <strong>{monitoredCount}</strong>
          </p>
          <div className="manage-filters" role="group" aria-label="列表筛选">
            {(
              [
                ['all', `全部 (${creators.length})`],
                ['on', `已监控 (${monitoredCount})`],
                ['off', `未监控 (${creators.length - monitoredCount})`],
              ] as const
            ).map(([f, label]) => (
              <button
                key={f}
                type="button"
                className={`chip${filter === f ? ' active' : ''}`}
                data-manage-filter={f}
                onClick={() => setFilter(f)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="manage-add">
          <input
            type="url"
            id="manage-add-url"
            placeholder="粘贴博主主页 URL（抖音 / B 站）"
            aria-label="博主 URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button type="button" className="btn btn-primary" id="btn-add-creator" onClick={() => void addCreator()}>
            添加博主
          </button>
        </div>
      </header>

      <div className="manage-body">
        <div className="manage-list-scroll" id="manage-list" role="list" aria-label="已登记博主">
          {loading ? <p className="hint">加载…</p> : null}
          {!loading && !filtered.length ? <p className="hint">筛选无结果</p> : null}
          {filtered.map((c) => (
            <Fragment key={c.id}>
              <div
                className={`manage-row${selectedId === c.id ? ' selected' : ''}${!c.monitor_enabled ? ' dimmed' : ''}`}
                role="listitem"
                tabIndex={0}
                data-creator={c.id}
                aria-expanded={selectedId === c.id}
                onClick={() => selectCreator(c.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    selectCreator(c.id);
                  }
                }}
              >
                <CreatorAvatar
                  creatorId={c.id}
                  displayName={c.display_name}
                  avatarUrl={c.avatar_url}
                  profileSyncedAt={c.profile_synced_at}
                  light={c.status_light}
                  abbr={c.status_abbr}
                  statusLabel={c.status_label}
                />
                <div className="manage-row-info">
                  <div className="manage-row-name">{c.display_name ?? c.unique_id ?? c.id}</div>
                  <div className="manage-row-meta">
                    <span className="platform-tag">{c.platform}</span>
                    <span className="manage-status-text">{manageStatusText(c)}</span>
                    {c.profile_stale ? <span className="tag warn">资料过期</span> : null}
                    {syncBusy?.startsWith(`${c.id}:`) ? <span className="tag">同步中</span> : null}
                  </div>
                </div>
                <div className="manage-row-pills">
                  {(() => {
                    const pill = autoRecordPillLabel(c.monitor_enabled, c.auto_record_override);
                    return <span className={pill.className}>{pill.text}</span>;
                  })()}
                </div>
                <div className="manage-row-monitor">
                  <span className="manage-row-monitor-label">监控</span>
                  <button
                    type="button"
                    className={`toggle${c.monitor_enabled ? ' on' : ''} manage-monitor-toggle`}
                    aria-label="监控开关"
                    aria-pressed={c.monitor_enabled}
                    onClick={(e) => {
                      e.stopPropagation();
                      void toggleMonitor(c);
                    }}
                  />
                </div>
              </div>
              {selectedId === c.id && selected?.id === c.id ? (
                <ManageCreatorDrawer
                  creator={selected}
                  globalAutoRecord={globalAutoRecord}
                  syncBusy={syncBusy}
                  onToggleMonitor={(creator) => void toggleMonitor(creator)}
                  onToggleContentSync={(creator) => void toggleContentSync(creator)}
                  onSetAutoRecord={(value) => void setAutoRecord(value)}
                  onRunSync={(kind) => void runSync(kind)}
                  onRemove={requestRemove}
                />
              ) : null}
            </Fragment>
          ))}
        </div>
      </div>

      <ConfirmDialog
        open={removeTarget != null}
        title="移除博主"
        message={removeTarget ? `确定移除 ${removeTarget.label}？此操作不可撤销。` : ''}
        confirmLabel="移除"
        danger
        onConfirm={() => void confirmRemove()}
        onCancel={() => setRemoveTarget(null)}
      />
    </div>
  );
}
