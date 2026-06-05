import { LivePlayer } from '../live/LivePlayer';
import { useLiveStatus } from '../live/useLiveStatus';

type Props = {
  active?: boolean;
  creatorId: string | null;
  showRecordBanner?: boolean;
  onRecordingStarted?: () => void;
};

export function ViewLive({ active, creatorId, showRecordBanner = false, onRecordingStarted }: Props) {
  const { refresh } = useLiveStatus(creatorId);

  return (
    <div className={`center-view${active ? ' active' : ''}`} id="view-live">
      <LivePlayer
        creatorId={creatorId}
        sessionId={null}
        showRecordBanner={showRecordBanner}
        onRecordingStarted={() => {
          void refresh();
          onRecordingStarted?.();
        }}
      />
    </div>
  );
}
