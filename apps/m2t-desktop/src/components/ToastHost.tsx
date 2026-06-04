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
