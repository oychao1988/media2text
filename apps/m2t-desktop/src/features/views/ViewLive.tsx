import { LivePlayer } from '../live/LivePlayer';
import { useLiveStatus } from '../live/useLiveStatus';

type Props = {
  active?: boolean;
  creatorId: string | null;
  showRecordBanner?: boolean;
  onRecordingStarted?: () => void;
};

export function ViewLive({ active, creatorId, showRecordBanner = false, onRecordingStarted }: Props) {
  const { activeSessionId } = useLiveStatus(creatorId);

  return (
    <div className={`center-view${active ? ' active' : ''}`} id="view-live">
      <LivePlayer
        creatorId={creatorId}
        sessionId={activeSessionId}
        showRecordBanner={showRecordBanner}
        onRecordingStarted={() => {
          onRecordingStarted?.();
        }}
      />
    </div>
  );
}
