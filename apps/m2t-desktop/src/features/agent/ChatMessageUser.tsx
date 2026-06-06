import { showToast } from '../../lib/toast';
import { USER_DISPLAY_NAME, userDisplayInitial } from '../layout/userDisplay';
import { formatChatTime } from './formatChatTime';
import { IconCopy, IconEdit, IconRetry } from './chatMessageIcons';
import { ChatMarkdown } from './ChatMarkdown';

type ChatMessageUserProps = {
  text: string;
  createdAt?: string | null;
};

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    showToast('已复制', 'success');
  } catch {
    showToast('复制失败', 'error');
  }
}

export function ChatMessageUser({ text, createdAt }: ChatMessageUserProps) {
  const timeLabel = formatChatTime(createdAt);

  return (
    <article className="chat-msg chat-msg-user">
      <div className="chat-msg-head">
        {timeLabel ? (
          <time className="chat-msg-time" dateTime={createdAt ?? undefined}>
            {timeLabel}
          </time>
        ) : (
          <span className="chat-msg-time chat-msg-time--placeholder" aria-hidden="true" />
        )}
        <span className="chat-msg-name">{USER_DISPLAY_NAME}</span>
        <span className="chat-msg-avatar user" aria-hidden="true">
          {userDisplayInitial()}
        </span>
      </div>
      <div className="chat-msg-bubble">
        <ChatMarkdown text={text} />
      </div>
      <div className="chat-msg-actions">
        <button
          type="button"
          className="chat-msg-action"
          title="重试"
          aria-label="重试"
          onClick={() => showToast('重试（即将支持）', 'info')}
        >
          <IconRetry />
          <span>重试</span>
        </button>
        <button
          type="button"
          className="chat-msg-action"
          title="编辑"
          aria-label="编辑"
          onClick={() => showToast('编辑（即将支持）', 'info')}
        >
          <IconEdit />
        </button>
        <button
          type="button"
          className="chat-msg-action"
          title="复制"
          aria-label="复制"
          onClick={() => void copyText(text)}
        >
          <IconCopy />
        </button>
      </div>
    </article>
  );
}
