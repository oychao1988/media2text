import { forwardRef, useImperativeHandle, useState } from 'react';
import { showToast } from '../../lib/toast';
import type { ConfigDto, LlmProvider } from '../../lib/types';

export function llmProvidersForPatch(providers: LlmProvider[]): Record<string, unknown>[] {
  return providers.map((p) => {
    const { configured, connected, ...rest } = p;
    const out: Record<string, unknown> = { ...rest };
    if (p.api_key?.trim()) {
      out.api_key = p.api_key.trim();
    }
    return out;
  });
}

function providerConnStatus(connected: boolean | null | undefined): {
  label: string;
  className: string;
} {
  if (connected === true) return { label: '已连通', className: 'ok' };
  if (connected === false) return { label: '未连通', className: 'warn' };
  return { label: '未检测', className: 'dim' };
}

function providerInitials(name: string): string {
  const n = (name || '').trim();
  if (!n) return '?';
  if (/[\u4e00-\u9fff]/.test(n[0]!)) return n[0]!;
  const parts = n.split(/[\s_-]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0]![0]! + parts[1]![0]!).toUpperCase();
  return n.slice(0, 2).toUpperCase();
}

export type ConfigAiPanelHandle = {
  addProvider: () => void;
};

type Props = {
  draft: ConfigDto;
  onChange: (providers: LlmProvider[], activeProviderId?: string) => void;
  onEditingChange?: (editing: boolean) => void;
  onSaveProvider?: (index: number) => Promise<void>;
  onRefresh?: () => Promise<void>;
  saving?: boolean;
};

export const ConfigAiPanel = forwardRef<ConfigAiPanelHandle, Props>(function ConfigAiPanel(
  { draft, onChange, onEditingChange, onSaveProvider, onRefresh, saving = false },
  ref,
) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const providers = draft.llmProviders;

  const openEdit = async (index: number) => {
    const target = providers[index];
    const needsKeyRefresh = Boolean(target?.configured && !target?.api_key?.trim());
    if (onRefresh && needsKeyRefresh) {
      try {
        await onRefresh();
      } catch {
        showToast('刷新 Provider 配置失败', 'error');
      }
    }
    setEditingIndex(index);
    onEditingChange?.(true);
  };

  const openNewEdit = (index: number) => {
    setEditingIndex(index);
    onEditingChange?.(true);
  };

  const setEditing = (index: number | null) => {
    if (index != null) {
      void openEdit(index);
      return;
    }
    setEditingIndex(null);
    onEditingChange?.(false);
  };

  const addProvider = () => {
    const next: LlmProvider = {
      name: `provider_${providers.length + 1}`,
      base_url: 'https://integrate.api.nvidia.com/v1',
      api_key_envs: [],
      models: [],
      configured: false,
      connected: null,
      api_key: null,
    };
    const list = [...providers, next];
    onChange(list);
    openNewEdit(list.length - 1);
  };

  useImperativeHandle(ref, () => ({ addProvider }), [providers.length]);

  const copyProvider = (index: number) => {
    const src = providers[index];
    if (!src) return;
    onChange([
      ...providers,
      {
        ...src,
        name: `${src.name}_copy`,
        configured: false,
        connected: null,
        api_key: null,
      },
    ]);
  };

  const removeProvider = (index: number) => {
    if (providers.length <= 1) {
      showToast('至少保留一个 Provider', 'info');
      return;
    }
    const removed = providers[index]?.name;
    const list = providers.filter((_, i) => i !== index);
    const active =
      draft.activeProviderId === removed ? (list[0]?.name ?? '') : draft.activeProviderId;
    onChange(list, active || undefined);
    setEditing(null);
    showToast(`已删除 Provider「${removed ?? ''}」`, 'success');
  };

  const handleSaveProvider = async () => {
    if (editingIndex == null || !onSaveProvider) return;
    await onSaveProvider(editingIndex);
    setEditing(null);
  };

  const editing = editingIndex != null ? providers[editingIndex] : null;
  const editingActive = editingIndex != null && editing != null;

  return (
    <>
      <div id="config-ai-list-view" hidden={editingActive}>
        <p className="hint" style={{ margin: '0 0 10px' }}>
          OpenAI 兼容端点；模型类型 LLM 用于摘要/Agent，STT 用于转写。
        </p>
        <div id="llm-providers-list" className="provider-row-list" aria-live="polite">
          {!providers.length ? (
            <p className="hint">暂无 Provider，点击顶栏「添加 Provider」。</p>
          ) : (
            providers.map((p, pi) => {
              const conn = providerConnStatus(p.connected);
              return (
                <article key={`${p.name}-${pi}`} className="provider-row" data-provider-index={pi}>
                  <span className="provider-row-drag" aria-hidden="true" title="排序（暂未实现）">
                    ⋮⋮
                  </span>
                  <div className="provider-row-icon" aria-hidden="true">
                    {providerInitials(p.name)}
                  </div>
                  <div className="provider-row-body">
                    <div className="provider-row-name">{p.name || '未命名'}</div>
                    <div className="provider-row-url">{p.base_url || '未配置 Base URL'}</div>
                  </div>
                  <span
                    className={`provider-row-status ${conn.className}`}
                    title="API 连通性（GET /models 探测）"
                  >
                    {conn.label}
                  </span>
                  <div className="provider-row-actions">
                    <button
                      type="button"
                      className="provider-icon-btn btn-edit-provider"
                      title="编辑"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditing(pi);
                      }}
                    >
                      ✎
                    </button>
                    <button
                      type="button"
                      className="provider-icon-btn btn-copy-provider"
                      title="复制"
                      onClick={(e) => {
                        e.stopPropagation();
                        copyProvider(pi);
                      }}
                    >
                      ⧉
                    </button>
                    <button
                      type="button"
                      className="provider-icon-btn btn-remove-provider"
                      title="删除"
                      onClick={(e) => {
                        e.stopPropagation();
                        removeProvider(pi);
                      }}
                    >
                      🗑
                    </button>
                  </div>
                </article>
              );
            })
          )}
        </div>
      </div>
      <div id="config-ai-detail-view" hidden={!editingActive}>
        {editing ? (
          <>
            <div className="provider-detail-head">
              <button
                type="button"
                className="btn-ghost"
                id="btn-provider-back"
                onClick={() => setEditing(null)}
              >
                ← 返回列表
              </button>
              <span className="provider-detail-title" id="provider-detail-title">
                编辑 · {editing.name || '未命名'}
              </span>
              {onSaveProvider ? (
                <button
                  type="button"
                  className="btn btn-sm"
                  id="btn-provider-save"
                  disabled={saving}
                  onClick={() => void handleSaveProvider()}
                >
                  {saving ? '保存中…' : '保存'}
                </button>
              ) : null}
            </div>
            <ProviderDetailForm
              provider={editing}
              isDefault={draft.activeProviderId === editing.name}
              onChange={(p, makeDefault) => {
                const list = providers.map((x, i) => (i === editingIndex ? p : x));
                onChange(list, makeDefault ? p.name : undefined);
              }}
            />
          </>
        ) : null}
      </div>
    </>
  );
});

function ProviderDetailForm({
  provider,
  isDefault,
  onChange,
}: {
  provider: LlmProvider;
  isDefault: boolean;
  onChange: (p: LlmProvider, makeDefault: boolean) => void;
}) {
  const [showApiKey, setShowApiKey] = useState(false);
  const models = provider.models.length ? provider.models : [''];
  const apiKeyValue = provider.api_key ?? '';
  const apiKeyMissing = provider.configured && !apiKeyValue.trim();

  const setModels = (next: string[]) => {
    onChange({ ...provider, models: next.map((m) => m.trim()).filter(Boolean) }, isDefault);
  };

  return (
    <div className="setting-card" id="provider-detail-form">
      <div className="field-row">
        <label htmlFor="provider-name">名称</label>
        <div className="field-control">
          <input
            id="provider-name"
            type="text"
            className="config-input wide provider-name"
            value={provider.name}
            onChange={(e) => onChange({ ...provider, name: e.target.value }, isDefault)}
          />
        </div>
      </div>
      <div className="field-row">
        <label htmlFor="provider-base-url">Base URL</label>
        <div className="field-control">
          <input
            id="provider-base-url"
            type="url"
            className="config-input wide provider-base-url"
            placeholder="https://…/v1"
            value={provider.base_url}
            onChange={(e) => onChange({ ...provider, base_url: e.target.value }, isDefault)}
          />
        </div>
      </div>
      <div className="field-row">
        <label htmlFor="provider-api-key">API Key</label>
        <div className="field-control">
          <div className="secret-input-wrap">
            <input
              id="provider-api-key"
              type={showApiKey ? 'text' : 'password'}
              className="config-input wide secret-input"
              placeholder={provider.configured ? '留空表示不修改已保存的 Key' : '输入 API Key'}
              autoComplete="off"
              value={apiKeyValue}
              onChange={(e) =>
                onChange({ ...provider, api_key: e.target.value || null }, isDefault)
              }
            />
            <button
              type="button"
              className="secret-input-toggle"
              aria-label={showApiKey ? '隐藏 API Key' : '显示 API Key'}
              aria-pressed={showApiKey}
              onClick={() => setShowApiKey((v) => !v)}
            >
              {showApiKey ? '🙈' : '👁'}
            </button>
          </div>
          {apiKeyMissing ? (
            <p className="hint warn-text">
              已配置 Key 但未能从 API 读取。请完全退出并重新打开桌面端，或手动重启{' '}
              <code>media2text serve --port 8765</code>。
            </p>
          ) : null}
        </div>
      </div>
      <p className="hint">保存时将写入项目 `.env` 并自动探测连通性；保存后需重载 Agent。</p>
      <div className="toggle-row">
        <span>设为默认 Provider</span>
        <button
          type="button"
          className={`toggle${isDefault ? ' on' : ''}`}
          id="cfg-provider-active"
          aria-pressed={isDefault}
          aria-label="设为默认 Provider"
          onClick={() => onChange(provider, !isDefault)}
        />
      </div>
      <p className="hint" style={{ margin: '8px 0' }}>
        模型列表
      </p>
      <table className="provider-models">
        <thead>
          <tr>
            <th>模型 ID</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {models.map((m, mi) => (
            <tr key={mi} data-model-index={mi}>
              <td>
                <input
                  type="text"
                  className="config-input provider-model-id"
                  placeholder="模型 ID"
                  value={m}
                  onChange={(e) => {
                    const next = [...models];
                    next[mi] = e.target.value;
                    setModels(next);
                  }}
                />
              </td>
              <td style={{ width: 56, textAlign: 'right' }}>
                <button
                  type="button"
                  className="btn-ghost btn-remove-model"
                  onClick={() => setModels(models.filter((_, i) => i !== mi))}
                >
                  删除
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="provider-model-actions">
        <button
          type="button"
          className="btn btn-sm"
          id="btn-detail-add-model"
          onClick={() => setModels([...models, ''])}
        >
          添加模型
        </button>
      </div>
    </div>
  );
}
