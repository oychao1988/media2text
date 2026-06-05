import { useEffect, useMemo } from 'react';
import { getApiBaseUrl } from '../../lib/api';
import { useCreators } from '../creators/CreatorsContext';
import { LivePlayer } from '../live/LivePlayer';
import { useLiveStatus } from '../live/useLiveStatus';

type Props = {
  active?: boolean;
  keepStream?: boolean;
  creatorId: string | null;
  showRecordBanner?: boolean;
  onRecordingStarted?: () => void;
};

export function ViewLive({
  active,
  keepStream = false,
  creatorId,
  showRecordBanner = false,
  onRecordingStarted,
}: Props) {
  const { selected } = useCreators();
  const { activeSessionId, refresh } = useLiveStatus(creatorId);

  useEffect(() => {
    if ((active || keepStream) && creatorId) void getApiBaseUrl();
  }, [active, keepStream, creatorId]);

  const sessionId = useMemo(() => {
    if (activeSessionId) return activeSessionId;
    if (creatorId && selected?.id === creatorId) {
      return selected.active_session_id ?? null;
    }
    return null;
  }, [activeSessionId, creatorId, selected]);

  const viewClass = [
    'center-view',
    active ? 'active' : '',
    keepStream && !active ? 'pinned' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={viewClass} id="view-live" aria-hidden={!active}>
      <LivePlayer
        creatorId={creatorId}
        sessionId={sessionId}
        attachStream={keepStream}
        visible={Boolean(active)}
        showRecordBanner={showRecordBanner}
        onRecordingStarted={() => {
          void refresh();
          onRecordingStarted?.();
        }}
      />
    </div>
  );
}
