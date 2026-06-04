export type ToastKind = 'info' | 'error' | 'success';

export type ToastItem = {
  id: number;
  message: string;
  kind: ToastKind;
};

type Listener = (items: ToastItem[]) => void;

let nextId = 1;
let items: ToastItem[] = [];
const listeners = new Set<Listener>();

function emit() {
  listeners.forEach((l) => l([...items]));
}

export function getToastsSnapshot(): ToastItem[] {
  return items;
}

export function subscribeToasts(listener: Listener): () => void {
  listeners.add(listener);
  listener([...items]);
  return () => listeners.delete(listener);
}

export function showToast(message: string, kind: ToastKind = 'info', durationMs = 4500): void {
  const id = nextId++;
  items = [...items, { id, message, kind }];
  emit();
  window.setTimeout(() => {
    items = items.filter((t) => t.id !== id);
    emit();
  }, durationMs);
}

export function dismissToast(id: number): void {
  items = items.filter((t) => t.id !== id);
  emit();
}
