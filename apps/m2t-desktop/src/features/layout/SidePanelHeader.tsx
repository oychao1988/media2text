import type { ReactNode } from 'react';

type Props = {
  title: string;
  collapseLabel: string;
  side: 'left' | 'right';
  onCollapse: () => void;
  actions?: ReactNode;
};

export function SidePanelHeader({ title, collapseLabel, side, onCollapse, actions }: Props) {
  const chevron = side === 'left' ? '‹' : '›';

  return (
    <header className="panel-header side-panel-header">
      <h2 className="side-panel-title">{title}</h2>
      {actions ? <div className="side-panel-header-actions">{actions}</div> : null}
      <button
        type="button"
        className="icon-btn panel-collapse-btn"
        id={side === 'left' ? 'collapse-left' : 'collapse-right'}
        title={collapseLabel}
        aria-label={collapseLabel}
        onClick={onCollapse}
      >
        {chevron}
      </button>
    </header>
  );
}
