import { useState } from 'react';
import { M2tSelect } from '../../components/M2tSelect';
import { useAutoResizeTextarea } from './useAutoResizeTextarea';

type AgentComposerProps = {
  ready: boolean;
  blocked?: boolean;
  model: string;
  providerModels: string[];
  onModelChange: (model: string) => void;
  onSend: (text: string) => void;
};

function AttachIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      aria-hidden="true"
    >
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <circle cx="8.5" cy="10.5" r="1.5" />
      <path d="M21 16l-5.5-5.5a2 2 0 0 0-3 0L3 20" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 19V5" />
      <path d="M6 11l6-6 6 6" />
    </svg>
  );
}

export function AgentComposer({
  ready,
  blocked = false,
  model,
  providerModels,
  onModelChange,
  onSend,
}: AgentComposerProps) {
  const [text, setText] = useState('');
  const inputRef = useAutoResizeTextarea(text, 10);

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || !ready || blocked) return;
    onSend(trimmed);
    setText('');
  };

  const modelOptions = [
    { value: 'auto', label: 'Auto' },
    ...providerModels.map((m) => ({ value: m, label: m })),
  ];

  const placeholder = blocked
    ? '博主不一致，无法发送…'
    : ready
      ? '继续提问…'
      : 'Agent 启动中…';

  const controlsDisabled = !ready || blocked;

  return (
    <form
      className="composer agent-composer"
      id="agent-form"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <textarea
        ref={inputRef}
        className="agent-composer-input"
        rows={1}
        id="agent-input"
        placeholder={placeholder}
        aria-label="Agent 输入"
        value={text}
        disabled={!ready || blocked}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <div className="agent-composer-toolbar">
        <div className="agent-composer-left">
          <button
            type="button"
            className="agent-mode-pill"
            id="agent-mode-pill"
            title="Agent 模式"
            disabled={controlsDisabled}
          >
            <span className="agent-mode-icon" aria-hidden="true">
              ∞
            </span>
            <span>Agent</span>
            <span className="agent-mode-chevron" aria-hidden="true">
              ▾
            </span>
          </button>
          <span className="agent-model-wrap" title="选择模型">
            <M2tSelect
              id="agent-model-select"
              className="agent-model-select m2t-select m2t-select--ghost"
              ariaLabel="Agent 模型"
              value={model}
              disabled={controlsDisabled}
              options={modelOptions}
              onChange={onModelChange}
            />
          </span>
        </div>
        <div className="agent-composer-actions">
          <button
            type="button"
            className="agent-icon-btn"
            id="agent-ctx-btn"
            title="上下文"
            aria-label="上下文"
            disabled={controlsDisabled}
          >
            ◎
          </button>
          <button
            type="button"
            className="agent-icon-btn"
            id="agent-attach-btn"
            title="附件"
            aria-label="附件"
            disabled={controlsDisabled}
          >
            <AttachIcon />
          </button>
          <button
            type="submit"
            className="agent-send-btn"
            id="btn-agent-send"
            title="发送"
            aria-label="发送"
            disabled={controlsDisabled || !text.trim()}
          >
            <SendIcon />
          </button>
        </div>
      </div>
    </form>
  );
}
