import { useState } from 'react';

type AgentComposerProps = {
  ready: boolean;
  model: string;
  providerModels: string[];
  onModelChange: (model: string) => void;
  onSend: (text: string) => void;
};

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M12 19V5M5 12l7-7 7 7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function AgentComposer({
  ready,
  model,
  providerModels,
  onModelChange,
  onSend,
}: AgentComposerProps) {
  const [text, setText] = useState('');

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || !ready) return;
    onSend(trimmed);
    setText('');
  };

  return (
    <div className="composer" id="agent-composer-wrap">
      <div className="agent-composer" id="agent-composer">
        <textarea
          className="agent-composer-input"
          placeholder={ready ? '向 Agent 提问…' : 'Agent 启动中…'}
          value={text}
          disabled={!ready}
          rows={2}
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
            <button type="button" className="agent-mode-pill" disabled={!ready} title="Agent 模式">
              <span className="agent-mode-icon" aria-hidden="true">
                ∞
              </span>
              Agent
              <span className="agent-mode-chevron" aria-hidden="true">
                ▾
              </span>
            </button>
            <div className="agent-model-wrap">
              <select
                className="agent-model-select"
                id="agent-model-select"
                value={model}
                disabled={!ready}
                aria-label="模型"
                onChange={(e) => onModelChange(e.target.value)}
              >
                <option value="auto">auto</option>
                {providerModels.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="agent-composer-actions">
            <button type="button" className="agent-icon-btn" disabled={!ready} title="上下文" aria-label="上下文">
              @
            </button>
            <button type="button" className="agent-icon-btn" disabled={!ready} title="附件" aria-label="附件">
              📎
            </button>
            <button
              type="button"
              className="agent-send-btn"
              disabled={!ready || !text.trim()}
              aria-label="发送"
              onClick={submit}
            >
              <SendIcon />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
