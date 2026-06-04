type Props = {
  title: string;
  collapseLabel: string;
  side: 'left' | 'right';
  onCollapse: () => void;
};

export function SidePanelHeader({ title, collapseLabel, side, onCollapse }: Props) {
  const chevron = side === 'left' ? '‹' : '›';

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
        {chevron}
      </button>
    </header>
  );
}
