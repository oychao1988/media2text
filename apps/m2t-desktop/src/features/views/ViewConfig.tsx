export function ViewConfig() {
  return (
    <div className="center-view settings-page active" id="view-config">
      <div className="settings-head">
        <div className="settings-head-inner">
          <div className="settings-head-meta">
            <div className="config-segments" role="tablist" aria-label="配置分段">
              <button type="button" className="seg-btn active" role="tab" aria-selected>
                环境
              </button>
              <button type="button" className="seg-btn" role="tab">
                监控
              </button>
              <button type="button" className="seg-btn" role="tab">
                直播
              </button>
              <button type="button" className="seg-btn" role="tab">
                AI
              </button>
            </div>
          </div>
        </div>
      </div>
      <div className="settings-scroll">
        <div className="setting-card">
          <div className="setting-card-head">
            <h3>桌面偏好</h3>
          </div>
          <p className="hint">系统配置静态壳 · 表单接线见 P6/P7。</p>
        </div>
      </div>
    </div>
  );
}
