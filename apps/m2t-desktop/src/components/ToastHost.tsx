import { useSyncExternalStore } from 'react';
import { dismissToast, getToastsSnapshot, subscribeToasts } from '../lib/toast';

export function ToastHost() {
  const items = useSyncExternalStore(subscribeToasts, getToastsSnapshot, () => []);

  if (!items.length) return null;

  return (
    <div className="toast-host" role="status" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={`toast toast-${t.kind}`}>
          <span>{t.message}</span>
          <button
            type="button"
            className="toast-dismiss"
            aria-label="关闭"
            onClick={() => dismissToast(t.id)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
