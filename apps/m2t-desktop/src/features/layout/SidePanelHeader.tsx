type Props = {
  title: string;
  collapseLabel: string;
  onCollapse: () => void;
};

export function SidePanelHeader({ title, collapseLabel, onCollapse }: Props) {
  return (
    <header className="panel-header side-panel-header">
      <h2 className="side-panel-title">{title}</h2>
      <button
        type="button"
        className="icon-btn panel-collapse-btn"
        title={collapseLabel}
        aria-label={collapseLabel}
        onClick={onCollapse}
      >
        ‹
      </button>
    </header>
  );
}
