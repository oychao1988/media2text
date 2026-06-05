import { useCallback, useEffect, useState } from 'react';
import { apiGet } from '../../lib/api';
import type { ActiveRecording } from '../../lib/types';

type LiveStatusResponse = {
  ok: boolean;
  active_recordings: ActiveRecording[];
};

export function useLiveStatus(creatorId: string | null) {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [recording, setRecording] = useState<ActiveRecording | null>(null);

  const refresh = useCallback(async () => {
    if (!creatorId) {
      setActiveSessionId(null);
      setRecording(null);
      return;
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
      setActiveSessionId(null);
      setRecording(null);
    }
  }, [creatorId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { activeSessionId, recording, refresh };
}
