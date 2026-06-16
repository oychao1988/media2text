import { useEffect, useMemo } from 'react';
import { getApiBaseUrl } from '../../lib/api';
import { useCreators } from '../creators/CreatorsContext';
import { LivePlayer } from '../live/LivePlayer';
import { useLiveStatus } from '../live/useLiveStatus';

type Props = {
  active?: boolean;
  creatorId: string | null;
  showRecordBanner?: boolean;
  onRecordingStarted?: () => void;
};

export function ViewLive({
  active,
  creatorId,
  showRecordBanner = false,
  onRecordingStarted,
}: Props) {
  const { selected } = useCreators();
  const { activeSessionId, refresh } = useLiveStatus(creatorId);

  useEffect(() => {
    if (active && creatorId) void getApiBaseUrl();
  }, [active, creatorId]);

  const sessionId = useMemo(() => {
    if (activeSessionId) return activeSessionId;
    if (creatorId && selected?.id === creatorId) {
      return selected.active_session_id ?? null;
    }
    return null;
  }, [activeSessionId, creatorId, selected]);

  const viewClass = ['center-view', active ? 'active' : ''].filter(Boolean).join(' ');

  return (
    <div className={viewClass} id="view-live" aria-hidden={!active}>
      <LivePlayer
        creatorId={creatorId}
        sessionId={sessionId}
        attachStream={Boolean(active)}
        showRecordBanner={showRecordBanner}
        onRecordingStarted={() => {
          void refresh();
          onRecordingStarted?.();
        }}
      />
    </div>
  );
}
