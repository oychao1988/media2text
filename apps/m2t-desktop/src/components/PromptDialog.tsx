import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

type Props = {
  open: boolean;
  title: string;
  defaultValue?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: (value: string) => void;
  onCancel: () => void;
};

export function PromptDialog({
  open,
  title,
  defaultValue = '',
  confirmLabel = '确定',
  cancelLabel = '取消',
  onConfirm,
  onCancel,
}: Props) {
  const titleId = useId();
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState(defaultValue);

  useEffect(() => {
    if (!open) return;
    setValue(defaultValue);
    document.body.classList.add('confirm-open');
    inputRef.current?.focus();
    inputRef.current?.select();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.classList.remove('confirm-open');
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [defaultValue, onCancel, open]);

  if (!open) return null;

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onConfirm(trimmed);
  };

  return createPortal(
    <div className="confirm-overlay" role="presentation" onClick={onCancel}>
      <div
        className="confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="confirm-dialog-header">
          <h2 id={titleId} className="confirm-dialog-title">
            {title}
          </h2>
        </div>
        <input
          ref={inputRef}
          id={inputId}
          className="prompt-dialog-input"
          type="text"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              submit();
            }
          }}
        />
        <div className="confirm-dialog-actions">
          <button type="button" className="btn confirm-dialog-cancel" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className="btn confirm-dialog-confirm btn-primary"
            onClick={submit}
            disabled={!value.trim()}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
