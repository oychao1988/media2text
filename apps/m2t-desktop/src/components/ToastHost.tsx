import { useSyncExternalStore } from 'react';
import { dismissToast, getToastsSnapshot, subscribeToasts } from '../lib/toast';

export function ToastHost() {
  const item = useSyncExternalStore(subscribeToasts, getToastsSnapshot, () => null);

  if (!item) return null;

  return (
    <div
      className={`toast toast-${item.kind} show`}
      role="status"
      aria-live="polite"
      id="toast"
    >
      <span>{item.message}</span>
      {item.actionLabel && item.onAction ? (
        <button
          type="button"
          className="toast-action"
          onClick={() => {
            item.onAction?.();
            dismissToast(item.id);
          }}
        >
          {item.actionLabel}
        </button>
      ) : null}
      <button
        type="button"
        className="toast-dismiss"
        aria-label="关闭"
        onClick={() => dismissToast(item.id)}
      >
        ×
      </button>
    </div>
  );
}
