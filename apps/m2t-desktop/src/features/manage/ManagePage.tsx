import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiDelete, apiGet, apiPatch, apiPost } from '../../lib/api';
import { showToast } from '../../lib/toast';
import type { Creator } from '../../lib/types';
import {
  autoRecordPillLabel,
  creatorInitial,
  formatCreatorSub,
  statusAriaLabel,
} from '../creators/creatorUtils';
import { StatusLight } from '../creators/StatusLight';
import { useCreators } from '../creators/CreatorsContext';

type ManageFilter = 'all' | 'on' | 'off';

export function ManagePage() {
  const { refresh: refreshSidebar } = useCreators();
  const [creators, setCreators] = useState<Creator[]>([]);
  const [filter, setFilter] = useState<ManageFilter>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [syncBusy, setSyncBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiGet<{ ok: boolean; creators: Creator[] }>('/api/creators?all=1', true);
      setCreators(res.creators ?? []);
      setSelectedId((prev) => {
        if (prev && res.creators.some((c) => c.id === prev)) return prev;
        return res.creators[0]?.id ?? null;
      });
    } catch {
      setCreators([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    if (filter === 'on') return creators.filter((c) => c.monitor_enabled);
    if (filter === 'off') return creators.filter((c) => !c.monitor_enabled);
    return creators;
  }, [creators, filter]);

  const selected = creators.find((c) => c.id === selectedId) ?? null;
  const monitoredCount = creators.filter((c) => c.monitor_enabled).length;

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

  const patchCreator = async (id: string, body: Record<string, unknown>) => {
    await apiPatch(`/api/creators/${id}`, body);
    await load();
    await refreshSidebar();
  };

  const toggleMonitor = async (c: Creator) => {
    try {
      await patchCreator(c.id, { monitorEnabled: !c.monitor_enabled });
      showToast(c.monitor_enabled ? '已关闭监控' : '已开启监控', 'success');
    } catch {
      /* toast */
    }
  };

  const setAutoRecord = async (value: string) => {
    if (!selected) return;
    try {
      await patchCreator(selected.id, { autoRecordOverride: value });
    } catch {
      /* toast */
    }
  };

  const runSync = async (kind: 'profile' | 'catalog' | 'dynamics') => {
    if (!selected) return;
    const key = `${selected.id}:${kind}`;
    setSyncBusy(key);
    try {
      if (kind === 'profile') await apiPost(`/api/creators/${selected.id}/sync-profile`);
      else if (kind === 'catalog') await apiPost(`/api/creators/${selected.id}/sync`);
      else await apiPost(`/api/creators/${selected.id}/sync-dynamics`);
      showToast('同步完成', 'success');
      await load();
      await refreshSidebar();
    } catch {
      showToast('同步失败', 'error');
    } finally {
      setSyncBusy(null);
    }
  };

  const removeCreator = async () => {
    if (!selected) return;
    if (!window.confirm(`确定移除 ${selected.display_name ?? selected.id}？`)) return;
    try {
      await apiDelete(`/api/creators/${selected.id}`);
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
            <div
              key={c.id}
              className={`manage-row${selectedId === c.id ? ' selected' : ''}${!c.monitor_enabled ? ' dimmed' : ''}`}
              role="listitem"
              tabIndex={0}
              onClick={() => setSelectedId(c.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  setSelectedId(c.id);
                }
              }}
            >
              <div className="manage-avatar" aria-hidden="true">
                {creatorInitial(c.display_name)}
                <StatusLight light={c.status_light} abbr={c.status_abbr} />
              </div>
              <div className="manage-row-info">
                <div className="manage-row-name">{c.display_name ?? c.unique_id ?? c.id}</div>
                <div className="manage-row-meta">
                  <span className="platform-tag">{c.platform}</span>
                  <span className="manage-status-text">{statusAriaLabel(c.status_light)}</span>
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
          ))}

          {selected ? (
            <div className="manage-drawer open" id="manage-drawer" aria-label="博主详情抽屉" role="region">
              <div className="manage-drawer-collapse">
              <div className="manage-drawer-inner is-visible">
                <div className="inspector-head">
                  <div className="manage-avatar lg" id="detail-avatar" aria-hidden="true">
                    {creatorInitial(selected.display_name)}
                    <StatusLight light={selected.status_light} abbr={selected.status_abbr} />
                  </div>
                  <div className="inspector-head-text">
                    <h3 id="detail-name">{selected.display_name ?? selected.id}</h3>
                    <p className="sub" id="detail-sub">
                      {formatCreatorSub(selected)}
                    </p>
                  </div>
                  <div className="inspector-head-actions">
                    {selected.profile_url ? (
                      <a className="btn" id="detail-open-profile" href={selected.profile_url} target="_blank" rel="noreferrer">
                        打开主页
                      </a>
                    ) : null}
                    <button type="button" className="btn-ghost danger" id="detail-remove" onClick={() => void removeCreator()}>
                      移除博主
                    </button>
                  </div>
                </div>
                <div className="inspector-grid">
                  <section className="inspector-block">
                    <h4>监控</h4>
                    <p className="hint">开启后参与 daemon 直播轮询与录制流水线。</p>
                    <div className="toggle-row">
                      <span>直播检测 + 录制流水线</span>
                      <button
                        type="button"
                        className={`toggle${selected.monitor_enabled ? ' on' : ''}`}
                        id="detail-monitor-toggle"
                        aria-pressed={selected.monitor_enabled}
                        aria-label="开启监控"
                        onClick={() => void toggleMonitor(selected)}
                      />
                    </div>
                  </section>
                  <section className="inspector-block" id="detail-auto-record-section">
                    <h4>开录策略</h4>
                    <div className="detail-record-segments radio-group" id="detail-auto-record-group" role="radiogroup">
                      {(
                        [
                          ['inherit', '继承全局', '跟随全局设置'],
                          ['on', '始终自动', '检测到直播即开录'],
                          ['off', '仅手动', '需在直播 Tab 点「开始录制」'],
                        ] as const
                      ).map(([val, label, sub]) => (
                        <label key={val} className={`radio-opt${selected.auto_record_override === val ? ' selected' : ''}`}>
                          <input
                            type="radio"
                            name="auto-record"
                            value={val}
                            checked={selected.auto_record_override === val}
                            onChange={() => void setAutoRecord(val)}
                          />
                          <strong>{label}</strong>
                          <span>{sub}</span>
                        </label>
                      ))}
                    </div>
                  </section>
                  <section className="inspector-block ops">
                    <h4>运维</h4>
                    <div className="detail-actions">
                      <button
                        type="button"
                        className="btn-ghost"
                        id="detail-sync-profile"
                        disabled={syncBusy != null}
                        onClick={() => void runSync('profile')}
                      >
                        同步资料
                      </button>
                      <button
                        type="button"
                        className="btn-ghost"
                        id="detail-sync-catalog"
                        disabled={syncBusy != null}
                        onClick={() => void runSync('catalog')}
                      >
                        同步作品
                      </button>
                      {selected.platform === 'bilibili' ? (
                        <button
                          type="button"
                          className="btn-ghost"
                          id="detail-sync-dynamics"
                          disabled={syncBusy != null}
                          onClick={() => void runSync('dynamics')}
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
          ) : null}
        </div>
      </div>
    </div>
  );
}
