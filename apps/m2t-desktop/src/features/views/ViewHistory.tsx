type Props = { active?: boolean };

export function ViewHistory({ active }: Props) {
  return (
    <div className={`center-view${active ? ' active' : ''}`} id="view-history">
      <div className="history-toolbar">
        <button className="chip active" type="button" data-filter="all">
          全部
        </button>
        <button className="chip" type="button" data-filter="transcript">
          仅有转写
        </button>
        <button className="chip" type="button" data-filter="summary">
          仅有摘要
        </button>
        <input
          className="history-search"
          type="search"
          id="history-search"
          placeholder="搜索日期…"
          aria-label="搜索历史场次"
        />
      </div>
      <div className="history-list" id="history-list">
        <div className="history-group">
          <div className="history-group-title">2026-06-02</div>
          <div className="session-row selected" tabIndex={0} role="button">
            <div className="dot-col">
              <span className="dot" />
            </div>
            <div className="session-main">
              <div className="session-time">21:04 – 23:22</div>
              <div className="session-meta">
                <span>2h 18m</span>
                <span className="tag ok">completed</span>
              </div>
            </div>
            <div className="session-size">1.2 GB</div>
          </div>
        </div>
        <p className="view-shell-note">历史列表静态壳 · API 接线见 P6</p>
      </div>
    </div>
  );
}
