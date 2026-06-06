import { useState } from 'react';
import { replyDurationSeconds } from './formatReplyDuration';
import { ChatMarkdown } from './ChatMarkdown';

export type ChatMessageProcessProps = {
  /** Turn in progress: show phase label only, not expandable. */
  mode: 'active' | 'completed';
  phaseLabel?: string;
  durationMs?: number;
  thinkingText?: string;
};

export function ChatMessageProcess({
  mode,
  phaseLabel,
  durationMs,
  thinkingText,
}: ChatMessageProcessProps) {
  const [expanded, setExpanded] = useState(false);
  const hasThinking = Boolean(thinkingText?.trim());
  const canExpand = mode === 'completed' && hasThinking;
  const seconds = replyDurationSeconds(durationMs);

  const label =
    mode === 'active'
      ? (phaseLabel ?? '处理中…')
      : seconds != null
        ? `已处理 ${seconds} 秒`
        : '已处理';

  if (mode === 'active') {
    return (
      <div className="chat-msg-process chat-msg-process--active" aria-live="polite">
        <span className="chat-msg-process-icon" aria-hidden="true">
          ☰
        </span>
        <span>{label}</span>
      </div>
    );
  }

  if (!canExpand) {
    return (
      <div className="chat-msg-process chat-msg-process--static">
        <span className="chat-msg-process-icon" aria-hidden="true">
          ☰
        </span>
        <span>{label}</span>
      </div>
    );
  }

  return (
    <div className="chat-msg-process-wrap">
      <button
        type="button"
        className={`chat-msg-process${expanded ? ' chat-msg-process--expanded' : ''}`}
        title="查看处理过程"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="chat-msg-process-icon" aria-hidden="true">
          ☰
        </span>
        <span>{label}</span>
        <span className="chat-msg-process-chevron" aria-hidden="true">
          ›
        </span>
      </button>
      {expanded ? (
        <div className="chat-msg-process-body">
          <ChatMarkdown text={thinkingText ?? ''} />
        </div>
      ) : null}
    </div>
  );
}
