type Props = {
  threadId: string;
  x: number;
  y: number;
  onRename: () => void;
  onDelete: () => void;
  onClose: () => void;
};

export function AgentThreadContextMenu({ threadId, x, y, onRename, onDelete, onClose }: Props) {
  return (
    <>
      <button
        type="button"
        className="agent-context-backdrop"
        aria-label="关闭菜单"
        onClick={onClose}
      />
      <div
        className="agent-context-menu"
        id="agent-context-menu"
        role="menu"
        style={{ left: x, top: y }}
        data-thread-id={threadId}
      >
        <button type="button" className="agent-context-menu-item" role="menuitem" onClick={onRename}>
          重命名
        </button>
        <button
          type="button"
          className="agent-context-menu-item danger"
          role="menuitem"
          onClick={onDelete}
        >
          删除
        </button>
      </div>
    </>
  );
}
