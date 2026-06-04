export function ViewManage() {
  return (
    <div className="center-view manage-page active" id="view-manage">
      <div className="manage-toolbar">
        <h2>监控管理</h2>
        <button type="button" className="btn btn-primary btn-sm">
          添加博主
        </button>
      </div>
      <div className="manage-list-scroll">
        <p className="view-shell-note">博主登记与监控开关静态壳 · API 接线见 P6。</p>
      </div>
    </div>
  );
}
