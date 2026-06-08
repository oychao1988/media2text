import { useCallback, useEffect, useState } from 'react';
import { M2tSelect } from '../../components/M2tSelect';
import { AgentAttachmentStrip } from './AgentAttachmentStrip';
import { AgentMentionPopover } from './AgentMentionPopover';
import type { ContextAttachment, ContextMode } from './contextAttachment';
import {
  mentionRowToAttachment,
  parseMentionAtCaret,
  removeMentionSegment,
  type MentionDocumentRow,
} from './mentionDocuments';
import { useMentionSessionIndex } from './useMentionSessionIndex';
import { useAutoResizeTextarea } from './useAutoResizeTextarea';

type MentionCreator = { id: string; display_name: string | null };

type AgentComposerProps = {
  ready: boolean;
  blocked?: boolean;
  model: string;
  providerModels: string[];
  placeholder?: string;
  attachments?: ContextAttachment[];
  contextMode?: ContextMode;
  sidebarCreatorId?: string | null;
  mentionCreators?: MentionCreator[];
  onRemoveAttachment?: (id: string) => void;
  onAppendMentionAttachment?: (attachment: ContextAttachment) => void;
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
  placeholder: placeholderProp,
  attachments = [],
  contextMode = 'both',
  sidebarCreatorId = null,
  mentionCreators = [],
  onRemoveAttachment,
  onAppendMentionAttachment,
  onModelChange,
  onSend,
}: AgentComposerProps) {
  const [text, setText] = useState('');
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionStart, setMentionStart] = useState<number | null>(null);
  const [mentionQuery, setMentionQuery] = useState('');
  const [mentionActiveIndex, setMentionActiveIndex] = useState(0);
  const { ref: inputRef, onInput } = useAutoResizeTextarea(text, 10);

  const { rows: mentionRows, loading: mentionLoading } = useMentionSessionIndex(
    mentionCreators,
    mentionQuery,
    mentionOpen,
  );

  useEffect(() => {
    setMentionActiveIndex(0);
  }, [mentionQuery, mentionRows.length]);

  const closeMention = useCallback(() => {
    setMentionOpen(false);
    setMentionStart(null);
    setMentionQuery('');
    setMentionActiveIndex(0);
  }, []);

  const syncMentionFromInput = useCallback(
    (value: string, caret: number) => {
      const parsed = parseMentionAtCaret(value, caret);
      if (!parsed) {
        closeMention();
        return;
      }
      setMentionOpen(true);
      setMentionStart(parsed.start);
      setMentionQuery(parsed.query);
    },
    [closeMention],
  );

  const selectMentionRow = useCallback(
    (row: MentionDocumentRow) => {
      if (mentionStart == null || !onAppendMentionAttachment) return;
      const el = inputRef.current;
      const caret = el?.selectionStart ?? text.length;
      const nextText = removeMentionSegment(text, mentionStart, caret);
      setText(nextText);
      onAppendMentionAttachment(mentionRowToAttachment(row));
      closeMention();
      requestAnimationFrame(() => {
        el?.focus();
        const pos = mentionStart;
        el?.setSelectionRange(pos, pos);
      });
    },
    [closeMention, inputRef, mentionStart, onAppendMentionAttachment, text],
  );

  const insertAtTrigger = useCallback(() => {
    const el = inputRef.current;
    if (!el || !ready || blocked) return;
    const caret = el.selectionStart ?? text.length;
    const next = `${text.slice(0, caret)}@${text.slice(caret)}`;
    setText(next);
    const newCaret = caret + 1;
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(newCaret, newCaret);
      syncMentionFromInput(next, newCaret);
    });
  }, [blocked, inputRef, ready, syncMentionFromInput, text]);

  const submit = () => {
    if (mentionOpen) return;
    const trimmed = text.trim();
    if (!trimmed || !ready || blocked) return;
    onSend(trimmed);
    setText('');
    closeMention();
  };

  const modelOptions = [
    { value: 'auto', label: 'Auto' },
    ...providerModels.map((m) => ({ value: m, label: m })),
  ];

  const placeholder =
    placeholderProp ??
    (blocked
      ? '博主不一致，无法发送…'
      : ready
        ? '继续提问…'
        : 'Agent 启动中…');

  const controlsDisabled = !ready || blocked;

  return (
    <form
      className="composer agent-composer agent-composer-wrap"
      id="agent-form"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <AgentAttachmentStrip
        attachments={attachments}
        contextMode={contextMode}
        sidebarCreatorId={sidebarCreatorId}
        onRemove={onRemoveAttachment ?? (() => {})}
      />
      <div className="agent-composer-input-wrap">
        <AgentMentionPopover
          open={mentionOpen}
          rows={mentionRows}
          loading={mentionLoading}
          activeIndex={mentionActiveIndex}
          onActiveIndexChange={setMentionActiveIndex}
          onSelect={selectMentionRow}
        />
        <textarea
          ref={inputRef}
          className="agent-composer-input"
          rows={1}
          id="agent-input"
          placeholder={placeholder}
          aria-label="Agent 输入"
          value={text}
          disabled={!ready || blocked}
          onChange={(e) => {
            const value = e.target.value;
            setText(value);
            syncMentionFromInput(value, e.target.selectionStart ?? value.length);
          }}
          onInput={onInput}
          onKeyDown={(e) => {
            if (mentionOpen && mentionRows.length > 0) {
              if (e.key === 'ArrowDown') {
                e.preventDefault();
                setMentionActiveIndex((i) => Math.min(i + 1, mentionRows.length - 1));
                return;
              }
              if (e.key === 'ArrowUp') {
                e.preventDefault();
                setMentionActiveIndex((i) => Math.max(i - 1, 0));
                return;
              }
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                const row = mentionRows[mentionActiveIndex];
                if (row) selectMentionRow(row);
                return;
              }
            }
            if (e.key === 'Escape' && mentionOpen) {
              e.preventDefault();
              closeMention();
              return;
            }
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
      </div>
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
              preferPlacement="above"
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
            title="引用文档 @"
            aria-label="引用文档"
            disabled={controlsDisabled}
            onClick={insertAtTrigger}
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
