import type { RuntimeStatus } from '../../lib/types';

/** Merge WS runtime.health / queue.updated patch into full runtime snapshot. */
export function mergeRuntimePatch(
  prev: RuntimeStatus | null,
  patch: Record<string, unknown>,
): RuntimeStatus | null {
  if (!prev) {
    return patch as RuntimeStatus;
  }
  const next: RuntimeStatus = { ...prev, ...patch } as RuntimeStatus;
  if (patch.daemon && typeof patch.daemon === 'object') {
    next.daemon = { ...prev.daemon, ...(patch.daemon as RuntimeStatus['daemon']) };
  }
  if (patch.recordings && typeof patch.recordings === 'object') {
    next.recordings = {
      ...prev.recordings,
      ...(patch.recordings as Partial<RuntimeStatus['recordings']>),
    };
  }
  if (patch.queues && typeof patch.queues === 'object') {
    next.queues = { ...prev.queues, ...(patch.queues as RuntimeStatus['queues']) };
  }
  if (patch.observability && typeof patch.observability === 'object') {
    next.observability = {
      ...prev.observability,
      ...(patch.observability as RuntimeStatus['observability']),
    };
  }
  return next;
}
