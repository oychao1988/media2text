import { apiPost } from '../../lib/api';
import { showToast } from '../../lib/toast';

type Props = {
  creatorId: string;
  visible: boolean;
  onStarted?: () => void;
};

export function RecordBanner({ creatorId, visible, onStarted }: Props) {
  if (!visible) return null;

  const startRecording = async () => {
    try {
      await apiPost(`/api/creators/${creatorId}/recording/start`);
      showToast('已开始录制', 'success');
      onStarted?.();
    } catch {
      /* api toast */
    }
  };

  return (
    <div className="record-banner" id="record-banner">
      <div className="record-banner-text">
        <strong>平台正在直播，尚未开始录制</strong>
        <span>监控开启且开录策略允许时 daemon 会自动录制；也可手动开始。</span>
      </div>
      <button className="btn btn-record" type="button" id="btn-start-record" onClick={() => void startRecording()}>
        开始录制
      </button>
    </div>
  );
}
