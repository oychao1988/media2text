import { useCallback, useEffect, useMemo, useState } from 'react';
import { requestAgentReload } from '../agent/agentSidecar';
import { apiGet, apiPatch, apiPost, ApiError } from '../../lib/api';
import { showToast } from '../../lib/toast';
import type { AuthPlatformStatus, ConfigDto } from '../../lib/types';
import { writeStoredTheme, type ThemeMode } from '../../lib/theme';
import { useDaemonActions } from '../daemon/DaemonCard';

type Segment = 'user' | 'monitor' | 'live' | 'ai';

const SEGMENTS: { id: Segment; label: string }[] = [
  { id: 'user', label: '环境' },
  { id: 'monitor', label: '监控' },
  { id: 'live', label: '直播' },
  { id: 'ai', label: 'AI' },
];

function Toggle({
  id,
  pressed,
  label,
  onToggle,
}: {
  id: string;
  pressed: boolean;
  label: string;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      className={`toggle${pressed ? ' on' : ''}`}
      id={id}
      aria-pressed={pressed}
      aria-label={label}
      onClick={onToggle}
    />
  );
}

export function ConfigForm() {
  const [segment, setSegment] = useState<Segment>('user');
  const [saved, setSaved] = useState<ConfigDto | null>(null);
  const [draft, setDraft] = useState<ConfigDto | null>(null);
  const [auth, setAuth] = useState<Record<string, AuthPlatformStatus>>({});
  const [doctor, setDoctor] = useState<Record<string, unknown> | null>(null);
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Set<string>>(new Set());
  const { restartDaemon } = useDaemonActions();

  const load = useCallback(async () => {
    const [cfgRes, authRes] = await Promise.all([
      apiGet<{ ok: boolean; config: ConfigDto }>('/api/config', true),
      apiGet<{ ok: boolean; platforms: Record<string, AuthPlatformStatus> }>('/api/auth/status', true),
    ]);
    setSaved(cfgRes.config);
    setDraft(cfgRes.config);
    setAuth(authRes.platforms ?? {});
  }, []);

  useEffect(() => {
    void load();
    void apiGet<Record<string, unknown>>('/api/health', true).then(setDoctor).catch(() => setDoctor(null));
  }, [load]);

  const dirty = useMemo(() => {
    if (!saved || !draft) return false;
    return JSON.stringify(saved) !== JSON.stringify(draft);
  }, [saved, draft]);

  const patchDraft = <K extends keyof ConfigDto>(key: K, value: ConfigDto[K]) => {
    setDraft((d) => (d ? { ...d, [key]: value } : d));
    if (key === 'theme') {
      writeStoredTheme(value as ThemeMode);
    }
  };

  const revert = () => {
    if (saved) {
      setDraft({ ...saved });
      writeStoredTheme(saved.theme as ThemeMode);
      setFieldErrors(new Set());
    }
  };

  const save = async () => {
    if (!draft || !saved || !dirty) return;
    setSaving(true);
    setFieldErrors(new Set());
    const body: Partial<ConfigDto> = {};
    (Object.keys(draft) as (keyof ConfigDto)[]).forEach((k) => {
      if (draft[k] !== saved[k]) (body as Record<string, unknown>)[k] = draft[k];
    });
    try {
      const res = await apiPatch<{
        ok: boolean;
        config: ConfigDto;
        requires_daemon_restart?: string[];
        requires_agent_reload?: string[];
      }>('/api/config', body);
      setSaved(res.config);
      setDraft(res.config);
      showToast('配置已保存', 'success');
      if (res.requires_daemon_restart?.length) {
        showToast('部分配置需重启守护进程后生效', 'info', 6000);
        if (window.confirm('是否立即重启守护进程？')) void restartDaemon();
      }
      if (res.requires_agent_reload?.length) {
        showToast('Agent 配置已更新，当前轮次结束后将重载', 'info');
        requestAgentReload();
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setFieldErrors(new Set(Object.keys(body)));
      }
    } finally {
      setSaving(false);
    }
  };

  const loginPlatform = async (platform: string) => {
    try {
      await apiPost(`/api/auth/login/${platform}`);
      showToast(`已发起 ${platform} 登录`, 'success');
      const authRes = await apiGet<{ platforms: Record<string, AuthPlatformStatus> }>(
        '/api/auth/status',
        true,
      );
      setAuth(authRes.platforms ?? {});
    } catch {
      /* toast */
    }
  };

  const runDoctor = async () => {
    try {
      const res = await apiPost<Record<string, unknown>>('/api/doctor/run');
      setDoctor(res);
      showToast('环境检测完成', 'success');
    } catch {
      /* toast */
    }
  };

  if (!draft) {
    return (
      <div className="center-view settings-page active" id="view-config">
        <p className="hint">加载配置…</p>
      </div>
    );
  }

  const errCls = (key: string) => (fieldErrors.has(key) ? ' field-error' : '');

  return (
    <div className="center-view settings-page active" id="view-config">
      <div className="settings-head">
        <div className="settings-head-inner">
          <div className="settings-head-meta">
            <div className="config-segments" role="tablist" aria-label="配置分段">
              {SEGMENTS.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className={`seg-btn${segment === s.id ? ' active' : ''}`}
                  role="tab"
                  aria-selected={segment === s.id}
                  onClick={() => setSegment(s.id)}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
          <div className="settings-actions">
            <button type="button" className="btn btn-sm" disabled={!dirty || saving} onClick={revert}>
              撤销
            </button>
            <button type="button" className="btn btn-primary btn-sm" disabled={!dirty || saving} onClick={() => void save()}>
              {saving ? '保存中…' : '保存'}
            </button>
          </div>
        </div>
      </div>

      <div className="settings-scroll">
        <div className="config-panels-wrap" id="config-form">
          {segment === 'user' ? (
            <div className="config-panel active" id="config-panel-user" role="tabpanel">
              <div className="setting-card">
                <div className="setting-card-head">
                  <h3>桌面偏好</h3>
                </div>
                <div className={`field-row${errCls('theme')}`}>
                  <label htmlFor="cfg-theme">界面主题</label>
                  <div className="field-control">
                    <select
                      className="config-select"
                      id="cfg-theme"
                      value={draft.theme}
                      onChange={(e) => patchDraft('theme', e.target.value)}
                    >
                      <option value="light">亮色</option>
                      <option value="dark">暗色</option>
                    </select>
                  </div>
                </div>
                <div className="toggle-row">
                  <span>通知提示音</span>
                  <Toggle
                    id="cfg-notify-sound"
                    label="通知提示音"
                    pressed={draft.notifySound}
                    onToggle={() => patchDraft('notifySound', !draft.notifySound)}
                  />
                </div>
              </div>
              <div className="setting-card">
                <div className="setting-card-head">
                  <h3>环境自检</h3>
                </div>
                <div className="field-row">
                  <span className="field-label">Doctor</span>
                  <span className="field-readonly ok">{doctor?.doctor_ok ? '正常' : '待检测'}</span>
                </div>
                <div className="config-actions">
                  <button type="button" className="btn btn-sm" id="btn-config-doctor" onClick={() => void runDoctor()}>
                    重新检测
                  </button>
                </div>
              </div>
            </div>
          ) : null}

          {segment === 'monitor' ? (
            <div className="config-panel active" id="config-panel-monitor" role="tabpanel">
              <div className="setting-card">
                <div className="setting-card-head">
                  <h3>全局调度</h3>
                </div>
                {(
                  [
                    ['cfg-live-poll', 'livePollInterval', '直播检测间隔', draft.livePollInterval],
                    ['cfg-vod-poll', 'vodPollInterval', '作品同步间隔', draft.vodPollInterval],
                    ['cfg-vod-batch', 'maxCreatorsPerVodTick', '每轮同步博主数', draft.maxCreatorsPerVodTick],
                    ['cfg-scan-concurrency', 'scanConcurrency', '并行扫描博主数', draft.scanConcurrency],
                  ] as const
                ).map(([id, key, label, val]) => (
                  <div className={`field-row${errCls(key)}`} key={key}>
                    <label htmlFor={id}>{label}</label>
                    <div className="field-control">
                      <input
                        type="number"
                        className="config-input"
                        id={id}
                        value={val}
                        onChange={(e) => patchDraft(key, Number(e.target.value))}
                      />
                    </div>
                  </div>
                ))}
              </div>
              {(['douyin', 'bilibili'] as const).map((plat) => (
                <article className="platform-config-card" data-platform={plat} key={plat}>
                  <div className="platform-config-head">
                    <div className={`platform-config-icon ${plat}`}>{plat === 'douyin' ? '抖' : 'B'}</div>
                    <div className="platform-config-meta">
                      <strong>{plat === 'douyin' ? '抖音' : '哔哩哔哩'}</strong>
                    </div>
                    <button
                      type="button"
                      className="btn btn-sm auth-inline"
                      onClick={() => void loginPlatform(plat)}
                    >
                      {auth[plat]?.configured ? '已登录 · 重新登录' : `登录 ${plat}`}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          ) : null}

          {segment === 'live' ? (
            <div className="config-panel active" id="config-panel-live" role="tabpanel">
              <div className="setting-card">
                <div className="setting-card-head">
                  <h3>录制管线</h3>
                </div>
                <div className={`field-row${errCls('pipelineMode')}`}>
                  <label htmlFor="cfg-pipeline-mode">录制管线</label>
                  <select
                    id="cfg-pipeline-mode"
                    className="config-select"
                    value={draft.pipelineMode}
                    onChange={(e) => patchDraft('pipelineMode', e.target.value)}
                  >
                    <option value="streaming">流式（实时转写）</option>
                    <option value="legacy">传统（录后转写）</option>
                  </select>
                </div>
                <div className="toggle-row">
                  <span>全局自动开录</span>
                  <Toggle
                    id="cfg-auto-record"
                    label="全局自动开录"
                    pressed={draft.autoRecord}
                    onToggle={() => patchDraft('autoRecord', !draft.autoRecord)}
                  />
                </div>
                <div className="toggle-row">
                  <span>启用流式转写</span>
                  <Toggle
                    id="cfg-streaming-stt"
                    label="启用流式转写"
                    pressed={draft.streamingSttEnabled}
                    onToggle={() => patchDraft('streamingSttEnabled', !draft.streamingSttEnabled)}
                  />
                </div>
                <div className="field-row">
                  <span className="field-label">Deepgram API</span>
                  <span className="field-readonly ok">{draft.deepgramConfigured ? '已配置' : '未配置'}</span>
                </div>
              </div>
              <div className="setting-card">
                <div className="setting-card-head">
                  <h3>通知</h3>
                </div>
                <div className="toggle-row">
                  <span>启用通知</span>
                  <Toggle
                    id="cfg-notify-enabled"
                    label="启用通知"
                    pressed={draft.notifyEnabled}
                    onToggle={() => patchDraft('notifyEnabled', !draft.notifyEnabled)}
                  />
                </div>
                <div className={`field-row${errCls('feishuWebhookUrl')}`}>
                  <label htmlFor="cfg-feishu-webhook">飞书 Webhook</label>
                  <input
                    type="password"
                    className="config-input wide"
                    id="cfg-feishu-webhook"
                    placeholder="留空表示不修改"
                    onChange={(e) => patchDraft('feishuWebhookUrl', e.target.value || draft.feishuWebhookUrl)}
                  />
                </div>
              </div>
            </div>
          ) : null}

          {segment === 'ai' ? (
            <div className="config-panel active" id="config-panel-ai" role="tabpanel">
              <div className="setting-card">
                <div className="setting-card-head">
                  <h3>LLM Providers</h3>
                </div>
                <ul className="provider-row-list">
                  {draft.llmProviders.map((p) => (
                    <li key={p.name} className="provider-row">
                      <strong>{p.name}</strong>
                      <span>{p.base_url}</span>
                      <span className={p.configured ? 'tag ok' : 'tag'}>{p.configured ? '已配置' : '未配置'}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="setting-card" id="config-ai-agent-card">
                <div className="setting-card-head">
                  <h3>Agent 对话默认</h3>
                </div>
                <div className={`field-row${errCls('agentModel')}`}>
                  <label htmlFor="cfg-agent-model">默认模型</label>
                  <input
                    id="cfg-agent-model"
                    className="config-input"
                    value={draft.agentModel}
                    onChange={(e) => patchDraft('agentModel', e.target.value)}
                  />
                </div>
                <div className={`field-row${errCls('maxContextChars')}`}>
                  <label htmlFor="cfg-max-context">上下文上限</label>
                  <input
                    type="number"
                    id="cfg-max-context"
                    className="config-input"
                    value={draft.maxContextChars}
                    onChange={(e) => patchDraft('maxContextChars', Number(e.target.value))}
                  />
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
