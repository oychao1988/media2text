import type { ReactNode } from 'react';
import { showToast } from '../../lib/toast';
import { AgentAvatar, type AgentCreatorRef } from './AgentAvatar';
import type { AgentProfile } from './agentProfile';
import { ChatMessageProcess } from './ChatMessageProcess';
import { formatChatTime } from './formatChatTime';
import { formatReplyDurationLabel } from './formatReplyDuration';
import { IconCopy, IconThumbDown, IconThumbUp } from './chatMessageIcons';
import { ChatMarkdown } from './ChatMarkdown';

type ChatMessageAgentProps = {
  profile: AgentProfile;
  creators: AgentCreatorRef[];
  text: string;
  createdAt?: string | null;
  thinkingText?: string;
  durationMs?: number;
  /** Streaming turn: show phase row, hide completed thinking until done. */
  activePhaseLabel?: string;
  children?: ReactNode;
};

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    showToast('已复制', 'success');
  } catch {
    showToast('复制失败', 'error');
  }
}

export function ChatMessageAgent({
  profile,
  creators,
  text,
  createdAt,
  thinkingText,
  durationMs,
  activePhaseLabel,
  children,
}: ChatMessageAgentProps) {
  const timeLabel = formatChatTime(createdAt);
  const durationLabel = formatReplyDurationLabel(durationMs);
  const isActive = activePhaseLabel != null;
  return (
    <article className="chat-msg chat-msg-agent">
      <div className="chat-msg-head">
        <AgentAvatar profile={profile} creators={creators} size="msg" />
        <span className="chat-msg-name">{profile.name}</span>
        {timeLabel ? (
          <time className="chat-msg-time" dateTime={createdAt ?? undefined}>
            {timeLabel}
          </time>
        ) : (
          <span className="chat-msg-time chat-msg-time--placeholder" aria-hidden="true" />
        )}
      </div>
      {isActive || durationMs != null || thinkingText ? (
        <ChatMessageProcess
          mode={isActive ? 'active' : 'completed'}
          phaseLabel={activePhaseLabel}
          durationMs={durationMs}
          thinkingText={isActive ? undefined : thinkingText}
        />
      ) : null}
      {(text || children) && (
        <div className="chat-msg-body">
          {text ? <ChatMarkdown text={text} /> : null}
          {children}
        </div>
      )}
      {!isActive ? (
        <div className="chat-msg-footer">
          <button
            type="button"
            className="chat-msg-footer-btn"
            title="复制"
            aria-label="复制"
            onClick={() => void copyText(text)}
          >
            <IconCopy />
          </button>
          <button
            type="button"
            className="chat-msg-footer-btn"
            title="点赞"
            aria-label="点赞"
            onClick={() => showToast('点赞（即将支持）', 'info')}
          >
            <IconThumbUp />
          </button>
          <button
            type="button"
            className="chat-msg-footer-btn"
            title="点踩"
            aria-label="点踩"
            onClick={() => showToast('点踩（即将支持）', 'info')}
          >
            <IconThumbDown />
          </button>
          {durationLabel ? (
            <span className="chat-msg-footer-duration" aria-label={durationLabel}>
              {durationLabel}
            </span>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
