import { useState } from 'react';

type AgentComposerProps = {
  ready: boolean;
  model: string;
  providerModels: string[];
  onModelChange: (model: string) => void;
  onSend: (text: string) => void;
};

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
    <div className="agent-composer" id="agent-composer">
      <div className="agent-composer-toolbar">
        <label htmlFor="agent-model-select">模型</label>
        <select
          id="agent-model-select"
          value={model}
          disabled={!ready}
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
      <textarea
        className="agent-composer-input"
        placeholder={ready ? '向 Agent 提问…' : 'Agent 启动中…'}
        value={text}
        disabled={!ready}
        rows={3}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <button type="button" className="btn-primary agent-composer-send" disabled={!ready} onClick={submit}>
        发送
      </button>
    </div>
  );
}
