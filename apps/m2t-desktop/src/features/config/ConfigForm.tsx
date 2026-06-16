import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { M2tSelect } from '../../components/M2tSelect';
import { ConfigAiPanel, type ConfigAiPanelHandle, llmProvidersForPatch } from './ConfigAiPanel';
import { tavilyApiKeyForPatch } from './distillConfigPatch';
import { apiGet, apiPatch, apiPost, ApiError } from '../../lib/api';
import { showToast } from '../../lib/toast';
import type { AuthPlatformStatus, ConfigDto, LlmProvider } from '../../lib/types';
import { writeStoredTheme, type ThemeMode } from '../../lib/theme';
import { useDaemonActions } from '../daemon/DaemonCard';

type Segment = 'user' | 'monitor' | 'live' | 'ai';

const SEGMENTS: { id: Segment; label: string }[] = [
  { id: 'user', label: '环境' },
  { id: 'monitor', label: '监控' },
  { id: 'live', label: '直播' },
  { id: 'ai', label: 'AI' },
];

const STT_MODELS: Record<string, string[]> = {
  deepgram: ['nova-2', 'nova-3', 'nova-2-general'],
  whisper: ['small', 'medium', 'large-v3'],
  openai: ['whisper-1', 'gpt-4o-mini-transcribe'],
};

type DoctorCheck = { name: string; ok: boolean; hint?: string };

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

function doctorCheckOk(
  checks: DoctorCheck[] | undefined,
  name: string,
): boolean | undefined {
  return checks?.find((c) => c.name === name)?.ok;
}

function readonlyStatus(
  ok: boolean | undefined,
  okText = '正常',
  warnText = '异常',
  id?: string,
) {
  return (
    <span id={id} className={`field-readonly${ok ? ' ok' : ' warn'}`}>
      {ok === undefined ? '待检测' : ok ? okText : warnText}
    </span>
  );
}

function authStatusLabel(status: AuthPlatformStatus['status'], configured?: boolean): string {
  switch (status) {
    case 'ok':
      return '已登录';
    case 'expired':
      return '会话已失效';
    case 'unknown':
      return '无法验证';
    case 'missing':
      return '未登录';
    default:
      return configured ? '已保存会话' : '未登录';
  }
}

function authStatusClass(status: AuthPlatformStatus['status']): string {
  return status === 'ok' ? ' ok' : ' warn';
}

function PlatformAuthStatus({
  platform,
  auth,
  onLogin,
}: {
  platform: string;
  auth: Record<string, AuthPlatformStatus>;
  onLogin: (p: string) => void;
}) {
  const row = auth[platform];
  const status = row?.status;
  const configured = row?.configured;
  const label = authStatusLabel(status, configured);
  const loginLabel =
    status === 'ok' ? '重新登录' : status === 'expired' ? '重新登录' : '登录';
  return (
    <span
      id={`cfg-auth-status-${platform}`}
      className={`platform-config-status${authStatusClass(status)}`}
      title={row?.error ?? undefined}
    >
      {label}
      <button type="button" className="auth-inline" onClick={() => onLogin(platform)}>
        {loginLabel}
      </button>
    </span>
  );
}

function normalizeLlmProviders(providers: LlmProvider[]): LlmProvider[] {
  return providers.map((p) => ({
    ...p,
    api_key: p.api_key === '***' || !p.api_key?.trim() ? null : p.api_key,
  }));
}

function normalizeConfigDto(cfg: ConfigDto): ConfigDto {
  const providers = normalizeLlmProviders(cfg.llmProviders ?? []);
  const providerId =
    cfg.summarizeProviderId?.trim() ||
    cfg.activeProviderId?.trim() ||
    providers[0]?.name ||
    '';
  const provider =
    providers.find((p) => p.name === providerId) ?? providers[0];
  const resolvedProviderId = provider?.name ?? providerId;
  const models = provider?.models ?? [];
  const model =
    (cfg.summarizeModel?.trim() && models.includes(cfg.summarizeModel.trim())
      ? cfg.summarizeModel.trim()
      : '') ||
    models[0] ||
    cfg.summarizeModel?.trim() ||
    '';
  return {
    ...cfg,
    summarizeProviderId: resolvedProviderId,
    summarizeModel: model,
    activeProviderId: cfg.activeProviderId?.trim() || resolvedProviderId,
  };
}

export function ConfigForm() {
  const [segment, setSegment] = useState<Segment>('user');
  const [saved, setSaved] = useState<ConfigDto | null>(null);
  const [draft, setDraft] = useState<ConfigDto | null>(null);
  const [auth, setAuth] = useState<Record<string, AuthPlatformStatus>>({});
  const [doctor, setDoctor] = useState<{ doctor_ok?: boolean; checks?: DoctorCheck[] } | null>(
    null,
  );
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Set<string>>(new Set());
  const [aiProviderEditing, setAiProviderEditing] = useState(false);
  const aiPanelRef = useRef<ConfigAiPanelHandle>(null);
  const { restartDaemon } = useDaemonActions();

  const load = useCallback(async () => {
    const [cfgRes, authRes] = await Promise.all([
      apiGet<{ ok: boolean; config: ConfigDto }>('/api/config', true),
      apiGet<{ ok: boolean; platforms: Record<string, AuthPlatformStatus> }>('/api/auth/status', true),
    ]);
    setSaved(normalizeConfigDto(cfgRes.config));
    setDraft(normalizeConfigDto(cfgRes.config));
    setAuth(authRes.platforms ?? {});
  }, []);

  useEffect(() => {
    void load();
    void apiGet<{ doctor_ok?: boolean; checks?: DoctorCheck[] }>('/api/health', true)
      .then(setDoctor)
      .catch(() => setDoctor(null));
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

  const applyConfigResponse = async (res: {
    ok: boolean;
    config: ConfigDto;
    requires_daemon_restart?: string[];
    requires_agent_reload?: string[];
  }) => {
    setSaved(normalizeConfigDto(res.config));
    setDraft(normalizeConfigDto(res.config));
    if (res.requires_daemon_restart?.length) {
      showToast('部分配置需重启守护进程后生效', 'info', 6000);
      if (window.confirm('是否立即重启守护进程？')) void restartDaemon();
    }
    if (res.requires_agent_reload?.length) {
      showToast('Agent 配置已更新，下一轮对话将使用新配置', 'info');
    }
  };

  const providerConnLabel = (connected: boolean | null | undefined) => {
    if (connected === true) return '已连通';
    if (connected === false) return '未连通';
    return '未检测';
  };

  const saveLlmProviders = async (providersOverride?: LlmProvider[]): Promise<boolean> => {
    if (!draft) return false;
    const providers = providersOverride ?? draft.llmProviders;
    setSaving(true);
    setFieldErrors(new Set());
    try {
      const res = await apiPatch<{
        ok: boolean;
        config: ConfigDto;
        requires_daemon_restart?: string[];
        requires_agent_reload?: string[];
      }>('/api/config', {
        llmProviders: llmProvidersForPatch(providers),
        activeProviderId: draft.activeProviderId,
        summarizeProviderId: draft.summarizeProviderId,
      });
      await applyConfigResponse(res);
      const statuses = res.config.llmProviders
        .map((p) => `${p.name}: ${providerConnLabel(p.connected)}`)
        .join(' · ');
      showToast(`Provider 已保存（${statuses}）`, 'success', 7000);
      return true;
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setFieldErrors(new Set(['llmProviders']));
      }
      showToast('Provider 保存失败', 'error');
      return false;
    } finally {
      setSaving(false);
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
    if (body.llmProviders) {
      body.llmProviders = llmProvidersForPatch(body.llmProviders as LlmProvider[]) as ConfigDto['llmProviders'];
    } else if (segment === 'ai' && draft.llmProviders.length) {
      body.llmProviders = llmProvidersForPatch(draft.llmProviders) as ConfigDto['llmProviders'];
    }
    if ('tavilyApiKey' in body) {
      const key = tavilyApiKeyForPatch(body.tavilyApiKey as string | null | undefined);
      if (key) {
        body.tavilyApiKey = key;
      } else {
        delete body.tavilyApiKey;
      }
    }
    try {
      const res = await apiPatch<{
        ok: boolean;
        config: ConfigDto;
        requires_daemon_restart?: string[];
        requires_agent_reload?: string[];
      }>('/api/config', body);
      await applyConfigResponse(res);
      showToast('配置已保存', 'success');
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
        '/api/auth/status?refresh=1',
        true,
      );
      setAuth(authRes.platforms ?? {});
    } catch {
      /* toast */
    }
  };

  const runDoctor = async () => {
    try {
      const res = await apiPost<{ doctor_ok?: boolean; checks?: DoctorCheck[] }>('/api/doctor/run');
      setDoctor(res);
      showToast('环境检测完成', 'success');
    } catch {
      /* toast */
    }
  };

  const summarizeModels = useMemo(() => {
    if (!draft) return [];
    const provider =
      draft.llmProviders.find((x) => x.name === draft.summarizeProviderId) ??
      draft.llmProviders[0];
    const models = provider?.models ?? [];
    const current = draft.summarizeModel?.trim();
    if (current && !models.includes(current)) {
      return [current, ...models];
    }
    return models;
  }, [draft]);

  const patchSummarizeProvider = (providerId: string) => {
    setDraft((d) => {
      if (!d) return d;
      const provider =
        d.llmProviders.find((p) => p.name === providerId) ?? d.llmProviders[0];
      const nextModel = provider?.models?.[0] ?? d.summarizeModel ?? '';
      return { ...d, summarizeProviderId: providerId, summarizeModel: nextModel };
    });
  };

  const agentModelOptions = useMemo(() => {
    if (!draft) return [];
    const opts: { value: string; label: string }[] = [{ value: 'auto', label: '自动' }];
    for (const p of draft.llmProviders) {
      for (const m of p.models) {
        opts.push({ value: m, label: `${p.name} · ${m}` });
      }
    }
    return opts;
  }, [draft]);

  if (!draft) {
    return (
      <div className="center-view settings-page active" id="view-config">
        <p className="hint">加载配置…</p>
      </div>
    );
  }

  const errCls = (key: string) => (fieldErrors.has(key) ? ' field-error' : '');
  const checks = doctor?.checks;
  const ffmpegOk = doctorCheckOk(checks, 'ffmpeg');
  const playwrightOk =
    doctorCheckOk(checks, 'playwright_browser') ?? doctorCheckOk(checks, 'playwright');
  const deepgramOk =
    doctorCheckOk(checks, 'streaming_stt_deepgram') ?? draft.deepgramConfigured;

  const sttModels = STT_MODELS[draft.streamingSttEngine] ?? STT_MODELS.deepgram;

  return (
    <div className="center-view settings-page active" id="view-config">
      <div className="settings-head">
        <div className="settings-head-inner">
          <div className="settings-head-meta">
            <div className="config-segments" role="tablist" aria-label="配置分段" id="config-segments">
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
            <span
              className={`settings-save-hint${dirty ? ' dirty' : ' saved'}`}
              id="config-save-hint"
            >
              {dirty ? '未保存' : '已保存'}
            </span>
          </div>
          <div className="settings-head-actions">
            <button
              type="button"
              className="btn btn-sm config-head-add-provider"
              id="btn-add-llm-provider"
              hidden={segment !== 'ai' || aiProviderEditing}
              onClick={() => aiPanelRef.current?.addProvider()}
            >
              添加 Provider
            </button>
            <button
              type="button"
              className="btn"
              id="btn-config-revert"
              disabled={!dirty || saving}
              onClick={revert}
            >
              撤销
            </button>
            <button
              type="button"
              className="btn btn-primary"
              id="btn-config-save"
              disabled={!dirty || saving}
              onClick={() => void save()}
            >
              {saving ? '保存中…' : '保存'}
            </button>
          </div>
        </div>
      </div>

      <div className="settings-scroll">
        <div className="config-panels-wrap" id="config-form">
          <div
            className={`config-panel${segment === 'user' ? ' active' : ''}`}
            id="config-panel-user"
            role="tabpanel"
            hidden={segment !== 'user'}
          >
              <div className="setting-card">
                <div className="setting-card-head">
                  <h3>桌面偏好</h3>
                </div>
                <div className={`field-row${errCls('theme')}`}>
                  <label htmlFor="cfg-theme">界面主题</label>
                  <div className="field-control">
                    <M2tSelect
                      className="config-select m2t-select"
                      id="cfg-theme"
                      ariaLabel="界面主题"
                      value={draft.theme}
                      onChange={(v) => patchDraft('theme', v)}
                      options={[
                        { value: 'light', label: '亮色' },
                        { value: 'dark', label: '暗色' },
                      ]}
                    />
                  </div>
                </div>
                <p className="hint">切换后立即生效；保存后写入本地配置。</p>
                <div className="toggle-row">
                  <span>通知提示音</span>
                  <Toggle
                    id="cfg-notify-sound"
                    label="通知提示音"
                    pressed={draft.notifySound}
                    onToggle={() => patchDraft('notifySound', !draft.notifySound)}
                  />
                </div>
                <p className="hint">开启后，开播、录制完成等事件会播放系统提示音。</p>
              </div>
              <div className="setting-card">
                <div className="setting-card-head">
                  <h3>环境自检</h3>
                </div>
                <div className="field-row">
                  <span className="field-label">ffmpeg</span>
                  {readonlyStatus(ffmpegOk, '正常', '未找到', 'cfg-doctor-ffmpeg')}
                </div>
                <div className="field-row">
                  <span className="field-label">Playwright</span>
                  {readonlyStatus(playwrightOk, '正常', '未安装', 'cfg-doctor-playwright')}
                </div>
                <div className="field-row">
                  <span className="field-label">Deepgram 扩展</span>
                  {readonlyStatus(deepgramOk, '已安装', '未配置', 'cfg-doctor-deepgram')}
                </div>
                <div className="config-actions">
                  <button type="button" className="btn btn-sm" id="btn-config-doctor" onClick={() => void runDoctor()}>
                    重新检测
                  </button>
                </div>
              </div>
            </div>

          <div
            className={`config-panel${segment === 'monitor' ? ' active' : ''}`}
            id="config-panel-monitor"
            role="tabpanel"
            hidden={segment !== 'monitor'}
          >
              <div className="setting-card">
                <div className="setting-card-head">
                  <h3>全局调度</h3>
                </div>
                <div className={`field-row${errCls('livePollInterval')}`}>
                  <label htmlFor="cfg-live-poll">直播检测间隔</label>
                  <div className="field-control">
                    <input
                      type="number"
                      className="config-input"
                      id="cfg-live-poll"
                      min={5}
                      max={120}
                      value={draft.livePollInterval}
                      onChange={(e) => patchDraft('livePollInterval', Number(e.target.value))}
                    />
                    <span className="field-unit">秒</span>
                  </div>
                </div>
                <p className="hint">守护进程按此间隔轮询各博主是否开播/下播。</p>
                <div className={`field-row${errCls('vodPollInterval')}`}>
                  <label htmlFor="cfg-vod-poll">作品同步间隔</label>
                  <div className="field-control">
                    <input
                      type="number"
                      className="config-input"
                      id="cfg-vod-poll"
                      min={60}
                      max={3600}
                      value={draft.vodPollInterval}
                      onChange={(e) => patchDraft('vodPollInterval', Number(e.target.value))}
                    />
                    <span className="field-unit">秒</span>
                  </div>
                </div>
                <div className={`field-row${errCls('maxCreatorsPerVodTick')}`}>
                  <label htmlFor="cfg-vod-batch">每轮同步博主数</label>
                  <div className="field-control">
                    <input
                      type="number"
                      className="config-input"
                      id="cfg-vod-batch"
                      min={1}
                      max={20}
                      value={draft.maxCreatorsPerVodTick}
                      onChange={(e) => patchDraft('maxCreatorsPerVodTick', Number(e.target.value))}
                    />
                  </div>
                </div>
                <div className={`field-row${errCls('scanConcurrency')}`}>
                  <label htmlFor="cfg-scan-concurrency">并行扫描博主数</label>
                  <div className="field-control">
                    <input
                      type="number"
                      className="config-input"
                      id="cfg-scan-concurrency"
                      min={1}
                      max={16}
                      value={draft.scanConcurrency}
                      onChange={(e) => patchDraft('scanConcurrency', Number(e.target.value))}
                    />
                  </div>
                </div>
              </div>
              <p className="platform-section-title">媒体平台</p>
              <PlatformCard
                plat="douyin"
                title="抖音"
                subtitle="直播检测、作品同步与登录态"
                auth={auth}
                onLogin={loginPlatform}
                fields={[
                  {
                    id: 'cfg-douyin-live-poll',
                    key: 'douyinLivePoll',
                    label: '直播轮询',
                    value: draft.douyinLivePoll,
                    unit: '秒',
                  },
                  {
                    id: 'cfg-douyin-poll',
                    key: 'douyinPollInterval',
                    label: '作品列表轮询',
                    value: draft.douyinPollInterval,
                    unit: '秒',
                  },
                ]}
                patchDraft={patchDraft}
                errCls={errCls}
              />
              <PlatformCard
                plat="bilibili"
                title="哔哩哔哩"
                subtitle="直播 / 投稿 / 动态与登录态"
                auth={auth}
                onLogin={loginPlatform}
                fields={[
                  {
                    id: 'cfg-bili-live-poll',
                    key: 'biliLivePoll',
                    label: '直播轮询',
                    value: draft.biliLivePoll,
                    unit: '秒',
                  },
                  {
                    id: 'cfg-bili-archive-poll',
                    key: 'biliArchivePoll',
                    label: '投稿轮询',
                    value: draft.biliArchivePoll,
                    unit: '秒',
                  },
                  {
                    id: 'cfg-bili-dynamic-poll',
                    key: 'biliDynamicPoll',
                    label: '动态轮询',
                    value: draft.biliDynamicPoll,
                    unit: '秒',
                  },
                ]}
                patchDraft={patchDraft}
                errCls={errCls}
              />
              <p className="config-panel-footer">
                保存后将在下一轮监控周期生效；切换平台登录无需重启守护进程。
              </p>
            </div>

          <div
            className={`config-panel${segment === 'live' ? ' active' : ''}`}
            id="config-panel-live"
            role="tabpanel"
            hidden={segment !== 'live'}
          >
              <p className="config-callout warn" id="cfg-live-callout" role="note">
                切换录制管线后需重启监控守护进程。流式模式将启用实时转写（Deepgram）。
              </p>
              <div className="setting-card">
                <div className="setting-card-head">
                  <h3>录制管线</h3>
                </div>
                <div className={`field-row${errCls('pipelineMode')}`}>
                  <label htmlFor="cfg-pipeline-mode">录制管线</label>
                  <div className="field-control">
                    <M2tSelect
                      id="cfg-pipeline-mode"
                      className="config-select m2t-select"
                      ariaLabel="录制管线"
                      value={draft.pipelineMode}
                      onChange={(v) => patchDraft('pipelineMode', v)}
                      options={[
                        { value: 'streaming', label: '流式（实时转写，推荐）' },
                        { value: 'legacy', label: '传统（录后转写）' },
                      ]}
                    />
                  </div>
                </div>
                <div className="toggle-row">
                  <span>检测到直播后自动开录</span>
                  <Toggle
                    id="cfg-auto-record"
                    label="全局自动开录"
                    pressed={draft.autoRecord}
                    onToggle={() => patchDraft('autoRecord', !draft.autoRecord)}
                  />
                </div>
                <p className="hint">博主可在「监控管理」中设为继承全局、始终自动或仅手动。</p>
              </div>
              <div className="setting-card">
                <div className="setting-card-head">
                  <h3>实时转写</h3>
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
                <div className={`field-row${errCls('streamingSttEngine')}`}>
                  <label htmlFor="cfg-streaming-engine">转写引擎</label>
                  <div className="field-control">
                    <M2tSelect
                      id="cfg-streaming-engine"
                      className="config-select m2t-select"
                      ariaLabel="转写引擎"
                      value={draft.streamingSttEngine}
                      onChange={(v) => patchDraft('streamingSttEngine', v)}
                      options={[
                        { value: 'deepgram', label: 'Deepgram（云端，推荐）' },
                        { value: 'whisper', label: 'Whisper（本地，实验）' },
                        { value: 'openai', label: 'OpenAI（云端）' },
                      ]}
                    />
                  </div>
                </div>
                <div className={`field-row${errCls('streamingSttModel')}`}>
                  <label htmlFor="cfg-streaming-model">模型</label>
                  <div className="field-control">
                    <M2tSelect
                      id="cfg-streaming-model"
                      className="config-select m2t-select"
                      ariaLabel="模型"
                      value={draft.streamingSttModel}
                      onChange={(v) => patchDraft('streamingSttModel', v)}
                      options={sttModels.map((m) => ({ value: m, label: m }))}
                    />
                  </div>
                </div>
                <div className={`field-row${errCls('flushIntervalSec')}`}>
                  <label htmlFor="cfg-flush-interval">片段写入间隔</label>
                  <div className="field-control">
                    <input
                      type="number"
                      id="cfg-flush-interval"
                      className="config-input"
                      min={10}
                      max={120}
                      value={draft.flushIntervalSec}
                      onChange={(e) => patchDraft('flushIntervalSec', Number(e.target.value))}
                    />
                    <span className="field-unit">秒</span>
                  </div>
                </div>
                <p className="hint">流式识别每隔 N 秒将当前文本写入 transcript sidecar。</p>
                <div className={`field-row${errCls('offlineConfirmSec')}`}>
                  <label htmlFor="cfg-offline-confirm">下播确认等待</label>
                  <div className="field-control">
                    <input
                      type="number"
                      id="cfg-offline-confirm"
                      className="config-input"
                      min={15}
                      max={180}
                      value={draft.offlineConfirmSec}
                      onChange={(e) => patchDraft('offlineConfirmSec', Number(e.target.value))}
                    />
                    <span className="field-unit">秒</span>
                  </div>
                </div>
                <div className="field-row">
                  <span className="field-label">Deepgram API</span>
                  {readonlyStatus(
                    draft.deepgramConfigured,
                    '已配置',
                    '未配置',
                    'cfg-deepgram-status',
                  )}
                </div>
              </div>
              <div className="setting-card">
                <div className="setting-card-head">
                  <h3>摘要生成</h3>
                </div>
                <div className="toggle-row">
                  <span>启用摘要</span>
                  <Toggle
                    id="cfg-summarize-enabled"
                    label="启用摘要"
                    pressed={draft.summarizeEnabled}
                    onToggle={() => patchDraft('summarizeEnabled', !draft.summarizeEnabled)}
                  />
                </div>
                <div className={`field-row${errCls('summarizeProviderId')}`}>
                  <label htmlFor="cfg-summarize-provider">摘要服务</label>
                  <div className="field-control">
                    <M2tSelect
                      id="cfg-summarize-provider"
                      className="config-select m2t-select"
                      ariaLabel="摘要服务"
                      value={draft.summarizeProviderId || draft.llmProviders[0]?.name || ''}
                      onChange={patchSummarizeProvider}
                      disabled={draft.llmProviders.length === 0}
                      options={draft.llmProviders.map((p) => ({ value: p.name, label: p.name }))}
                    />
                  </div>
                </div>
                <div className={`field-row${errCls('summarizeModel')}`}>
                  <label htmlFor="cfg-summarize-model-live">摘要模型</label>
                  <div className="field-control">
                    <M2tSelect
                      id="cfg-summarize-model-live"
                      className="config-select m2t-select"
                      ariaLabel="摘要模型"
                      value={draft.summarizeModel || summarizeModels[0] || ''}
                      onChange={(v) => patchDraft('summarizeModel', v)}
                      disabled={summarizeModels.length === 0}
                      options={summarizeModels.map((m) => ({ value: m, label: m }))}
                    />
                  </div>
                </div>
                <p className="hint">摘要服务与模型来自「AI」中的 Provider。</p>
              </div>
              <article className="platform-config-card" data-platform="aliyundrive">
                <div className="platform-config-head">
                  <div className="platform-config-icon aliyundrive" aria-hidden="true">
                    云
                  </div>
                  <div className="platform-config-meta">
                    <strong>阿里云盘</strong>
                    <span>直播 MP4 与 sidecar 备份</span>
                  </div>
                  <PlatformAuthStatus platform="aliyundrive" auth={auth} onLogin={loginPlatform} />
                </div>
                <div className="platform-config-body">
                  <div className="toggle-row">
                    <span>直播结束后备份到云盘</span>
                    <Toggle
                      id="cfg-aliyun-enabled"
                      label="阿里云盘备份"
                      pressed={draft.aliyunEnabled}
                      onToggle={() => patchDraft('aliyunEnabled', !draft.aliyunEnabled)}
                    />
                  </div>
                  <div className={`field-row${errCls('aliyunRootFolder')}`}>
                    <label htmlFor="cfg-aliyun-root">云端根目录名称</label>
                    <div className="field-control">
                      <input
                        type="text"
                        className="config-input wide"
                        id="cfg-aliyun-root"
                        maxLength={64}
                        value={draft.aliyunRootFolder}
                        onChange={(e) => patchDraft('aliyunRootFolder', e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="toggle-row">
                    <span>上传成功后删除本地文件</span>
                    <Toggle
                      id="cfg-aliyun-delete-local"
                      label="删除本地"
                      pressed={draft.aliyunDeleteLocal}
                      onToggle={() => patchDraft('aliyunDeleteLocal', !draft.aliyunDeleteLocal)}
                    />
                  </div>
                  <div className="toggle-row">
                    <span>同时上传转写与摘要</span>
                    <Toggle
                      id="cfg-aliyun-upload-sidecar"
                      label="上传 sidecar"
                      pressed={draft.aliyunUploadSidecar}
                      onToggle={() => patchDraft('aliyunUploadSidecar', !draft.aliyunUploadSidecar)}
                    />
                  </div>
                </div>
              </article>
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
                  <div className="field-control">
                    <input
                      type="password"
                      className="config-input wide"
                      id="cfg-feishu-webhook"
                      placeholder={draft.feishuConfigured ? '留空表示不修改' : '填写即启用飞书通知'}
                      autoComplete="off"
                      onChange={(e) =>
                        patchDraft('feishuWebhookUrl', e.target.value || draft.feishuWebhookUrl)
                      }
                    />
                  </div>
                </div>
                <p className="hint">填写 Webhook 即走飞书推送；留空并保存表示不修改已保存地址。</p>
              </div>
              <p className="config-panel-footer">
                切换录制管线后需重启监控守护进程；其余项保存后按轮询或后处理队列生效。
              </p>
            </div>

          <div
            className={`config-panel${segment === 'ai' ? ' active' : ''}`}
            id="config-panel-ai"
            role="tabpanel"
            hidden={segment !== 'ai'}
          >
              <ConfigAiPanel
                ref={aiPanelRef}
                draft={draft}
                saving={saving}
                onRefresh={load}
                onEditingChange={setAiProviderEditing}
                onSaveProvider={async (_index, providers) => saveLlmProviders(providers)}
                onChange={(providers, activeId) => {
                  patchDraft('llmProviders', providers);
                  if (activeId != null) {
                    patchDraft('activeProviderId', activeId);
                    patchDraft('summarizeProviderId', activeId);
                  }
                }}
              />
              <div className="setting-card" id="cfg-distill-card" hidden={aiProviderEditing}>
                <div className="setting-card-head">
                  <h3>创作者蒸馏 Bootstrap</h3>
                </div>
                <div className="toggle-row">
                  <span>启用 Web 调研（Bootstrap）</span>
                  <Toggle
                    id="cfg-bootstrap-web-research"
                    label="启用 Web 调研"
                    pressed={draft.bootstrapWebResearch}
                    onToggle={() =>
                      patchDraft('bootstrapWebResearch', !draft.bootstrapWebResearch)
                    }
                  />
                </div>
                <p className="hint">
                  登记新博主时可用 Tavily 补充公开资料；关闭后仅使用本地语料。
                </p>
                <div className={`field-row${errCls('tavilyApiKey')}`}>
                  <label htmlFor="cfg-tavily-api-key">Tavily API Key</label>
                  <div className="field-control">
                    <input
                      type="password"
                      className="config-input wide"
                      id="cfg-tavily-api-key"
                      placeholder={draft.tavilyConfigured ? '留空表示不修改' : '填写以启用 Web 调研'}
                      autoComplete="off"
                      onChange={(e) =>
                        patchDraft('tavilyApiKey', e.target.value || draft.tavilyApiKey)
                      }
                    />
                  </div>
                </div>
                <div className="field-row">
                  <span className="field-label">Tavily API</span>
                  {readonlyStatus(
                    draft.tavilyConfigured,
                    '已配置',
                    '未配置',
                    'cfg-tavily-status',
                  )}
                </div>
                <p className="hint">
                  密钥写入项目 `.env`（{draft.tavilyApiKeyEnv}），保存后无需重启 sidecar。
                </p>
              </div>
              <div className="setting-card" id="config-ai-agent-card" hidden={aiProviderEditing}>
                  <div className="setting-card-head">
                    <h3>Agent 对话默认</h3>
                  </div>
                  <div className={`field-row${errCls('agentModel')}`}>
                    <label htmlFor="cfg-agent-model">默认模型</label>
                    <div className="field-control">
                      <M2tSelect
                        id="cfg-agent-model"
                        className="config-select m2t-select"
                        ariaLabel="默认模型"
                        value={draft.agentModel}
                        onChange={(v) => patchDraft('agentModel', v)}
                        options={agentModelOptions.map((o) => ({ value: o.value, label: o.label }))}
                      />
                    </div>
                  </div>
                  <div className={`field-row${errCls('maxContextChars')}`}>
                    <label htmlFor="cfg-max-context">上下文上限</label>
                    <div className="field-control">
                      <input
                        type="number"
                        id="cfg-max-context"
                        className="config-input"
                        min={4000}
                        max={128000}
                        step={1000}
                        value={draft.maxContextChars}
                        onChange={(e) => patchDraft('maxContextChars', Number(e.target.value))}
                      />
                      <span className="field-unit">字</span>
                    </div>
                  </div>
                  <p className="hint">右栏对话可按场次覆盖模型；与「直播」中的摘要默认模型可不同。</p>
                </div>
            </div>
        </div>
      </div>
    </div>
  );
}

type PlatformField = {
  id: string;
  key: keyof ConfigDto;
  label: string;
  value: number;
  unit?: string;
};

function PlatformCard({
  plat,
  title,
  subtitle,
  auth,
  onLogin,
  fields,
  patchDraft,
  errCls,
}: {
  plat: 'douyin' | 'bilibili';
  title: string;
  subtitle: string;
  auth: Record<string, AuthPlatformStatus>;
  onLogin: (p: string) => void;
  fields: PlatformField[];
  patchDraft: <K extends keyof ConfigDto>(key: K, value: ConfigDto[K]) => void;
  errCls: (key: string) => string;
}) {
  const icon = plat === 'douyin' ? '抖' : 'B';
  return (
    <article className="platform-config-card" data-platform={plat}>
      <div className="platform-config-head">
        <div className={`platform-config-icon ${plat}`} aria-hidden="true">
          {icon}
        </div>
        <div className="platform-config-meta">
          <strong>{title}</strong>
          <span>{subtitle}</span>
        </div>
        <PlatformAuthStatus platform={plat} auth={auth} onLogin={onLogin} />
      </div>
      <div className="platform-config-body">
        {fields.map((f) => (
          <div className={`field-row${errCls(f.key)}`} key={f.key}>
            <label htmlFor={f.id}>{f.label}</label>
            <div className="field-control">
              <input
                type="number"
                className="config-input"
                id={f.id}
                value={f.value}
                onChange={(e) => patchDraft(f.key, Number(e.target.value) as ConfigDto[typeof f.key])}
              />
              {f.unit ? <span className="field-unit">{f.unit}</span> : null}
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}
