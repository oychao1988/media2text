import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { SidePanelHeader } from './SidePanelHeader';

describe('SidePanelHeader', () => {
  it('shows ‹ for left panel collapse', () => {
    render(
      <SidePanelHeader title="监控" side="left" collapseLabel="折叠左栏" onCollapse={() => {}} />,
    );
    expect(screen.getByRole('button', { name: '折叠左栏' })).toHaveTextContent('‹');
  });

  it('shows › for right panel collapse', () => {
    render(
      <SidePanelHeader title="内容" side="right" collapseLabel="折叠右栏" onCollapse={() => {}} />,
    );
    expect(screen.getByRole('button', { name: '折叠右栏' })).toHaveTextContent('›');
  });

  it('calls onCollapse when clicked', async () => {
    const user = userEvent.setup();
    const onCollapse = vi.fn();
    render(
      <SidePanelHeader title="监控" side="left" collapseLabel="折叠左栏" onCollapse={onCollapse} />,
    );
    await user.click(screen.getByRole('button', { name: '折叠左栏' }));
    expect(onCollapse).toHaveBeenCalledOnce();
  });
});
