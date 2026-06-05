import { useCallback, useEffect, useState } from 'react';
import { apiGet } from '../../lib/api';
import type { ActiveRecording } from '../../lib/types';
import { useCreators } from '../creators/CreatorsContext';
import { useRuntime } from '../runtime/RuntimeContext';

type LiveStatusResponse = {
  ok: boolean;
  active_recordings: ActiveRecording[];
};

export function useLiveStatus(creatorId: string | null) {
  const { revision } = useCreators();
  const { runtime } = useRuntime();
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [recording, setRecording] = useState<ActiveRecording | null>(null);

  const refresh = useCallback(async () => {
    if (!creatorId) {
      setActiveSessionId(null);
      setRecording(null);
      return;
    }
    const fromRuntime =
      runtime?.recordings.items.find((r) => r.creator_id === creatorId) ?? null;
    if (fromRuntime) {
      setRecording(fromRuntime);
      setActiveSessionId(fromRuntime.session_id);
    }
    try {
      const res = await apiGet<LiveStatusResponse>(
        `/api/live/status?creator=${encodeURIComponent(creatorId)}`,
        true,
      );
      const match =
        res.active_recordings?.find((r) => r.creator_id === creatorId) ??
        res.active_recordings?.[0] ??
        null;
      setRecording(match);
      setActiveSessionId(match?.session_id ?? null);
    } catch {
      if (!fromRuntime) {
        setActiveSessionId(null);
        setRecording(null);
      }
    }
  }, [creatorId, runtime?.recordings.items]);

  useEffect(() => {
    void refresh();
  }, [refresh, revision]);

  return { activeSessionId, recording, refresh };
}
