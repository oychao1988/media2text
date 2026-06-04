type Props = { active?: boolean };

export function ViewLive({ active }: Props) {
  return (
    <div className={`center-view${active ? ' active' : ''}`} id="view-live">
      <div className="video-area">
        <div className="video-viewport">
          <div className="video-frame">
            <div className="video-placeholder">
              <div className="play-icon" aria-hidden="true">
                ▶
              </div>
              <p>HTTP-FLV 直播预览</p>
              <p className="video-placeholder-hint">
                平台流经 API 反向代理 · 与 ffmpeg 录制并行（P6 接线）
              </p>
            </div>
          </div>
        </div>
        <div className="record-banner" id="record-banner">
          <div className="record-banner-text">
            <strong>平台正在直播，尚未开始录制</strong>
            <span>监控开启且开录策略允许时 daemon 会自动录制。</span>
          </div>
          <button className="btn btn-record" type="button" id="btn-start-record">
            开始录制
          </button>
        </div>
      </div>
    </div>
  );
}
