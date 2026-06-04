export type ToastKind = 'info' | 'error' | 'success';

export type ToastItem = {
  id: number;
  message: string;
  kind: ToastKind;
};

type Listener = (item: ToastItem | null) => void;

let nextId = 1;
let current: ToastItem | null = null;
let hideTimer: number | undefined;
const listeners = new Set<Listener>();

function emit() {
  listeners.forEach((l) => l(current));
}

export function getToastsSnapshot(): ToastItem | null {
  return current;
}

export function subscribeToasts(listener: Listener): () => void {
  listeners.add(listener);
  listener(current);
  return () => listeners.delete(listener);
}

export function showToast(message: string, kind: ToastKind = 'info', durationMs = 4500): void {
  if (hideTimer !== undefined) {
    window.clearTimeout(hideTimer);
    hideTimer = undefined;
  }
  const id = nextId++;
  current = { id, message, kind };
  emit();
  hideTimer = window.setTimeout(() => {
    if (current?.id === id) {
      current = null;
      emit();
    }
    hideTimer = undefined;
  }, durationMs);
}

export function dismissToast(id: number): void {
  if (current?.id === id) {
    if (hideTimer !== undefined) {
      window.clearTimeout(hideTimer);
      hideTimer = undefined;
    }
    current = null;
    emit();
  }
}
