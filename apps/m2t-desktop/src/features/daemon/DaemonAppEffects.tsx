import { useEffect } from 'react';
import { useRuntime } from '../runtime/RuntimeContext';

/** Single place to sync daemon health → #app.daemon-stopped (avoids duplicate DaemonCard toggling). */
export function DaemonAppEffects() {
  const { runtime, loading } = useRuntime();
  const health = runtime?.health ?? 'stopped';

  useEffect(() => {
    document.getElementById('app')?.classList.toggle('daemon-stopped', health === 'stopped' && !loading);
  }, [health, loading]);

  return null;
}
