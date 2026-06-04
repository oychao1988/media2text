type Props = {
  onAddCreator: () => void;
};

export function CreatorListEmpty({ onAddCreator }: Props) {
  return (
    <div className="creator-list-empty" id="creator-list-empty">
      <p className="empty-title">暂无监控博主</p>
      <p className="empty-hint">在监控管理中添加博主并开启监控</p>
      <button type="button" className="btn btn-primary" id="btn-empty-add-creator" onClick={onAddCreator}>
        添加博主
      </button>
    </div>
  );
}
