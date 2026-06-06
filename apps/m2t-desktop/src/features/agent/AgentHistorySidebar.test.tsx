import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AgentHistorySidebar } from './AgentHistorySidebar';
import type { ThreadRow } from './types';

function makeThreads(n: number, prefix: string): ThreadRow[] {
  const now = Date.now();
  return Array.from({ length: n }, (_, i) => ({
    id: `${prefix}-${i}`,
    creator_id: 'c1',
    session_id: null,
    title: `${prefix} ${i}`,
    provider_name: null,
    model: 'auto',
    updated_at: new Date(now - i * 86400000).toISOString(),
  }));
}

describe('AgentHistorySidebar', () => {
  it('filters threads by search (A4)', async () => {
    const user = userEvent.setup();
    render(
      <AgentHistorySidebar
        threads={[
          {
            id: '1',
            creator_id: 'c1',
            session_id: null,
            title: 'Market recap',
            provider_name: null,
            model: 'auto',
            updated_at: new Date().toISOString(),
          },
          {
            id: '2',
            creator_id: 'c1',
            session_id: null,
            title: 'Other chat',
            provider_name: null,
            model: 'auto',
            updated_at: new Date().toISOString(),
          },
        ]}
        activeThreadId={null}
        onSelectThread={() => {}}
        onOpenMenu={() => {}}
        onRenameCommit={() => {}}
        onRenameCancel={() => {}}
      />,
    );

    expect(screen.getByText('Market recap')).toBeTruthy();
    await user.type(screen.getByPlaceholderText('搜索 Agent…'), 'market');
    expect(screen.queryByText('Other chat')).toBeNull();
  });

  it('shows time group headings (A4)', () => {
    render(
      <AgentHistorySidebar
        threads={makeThreads(1, 'Today')}
        activeThreadId={null}
        onSelectThread={() => {}}
        onOpenMenu={() => {}}
        onRenameCommit={() => {}}
        onRenameCancel={() => {}}
      />,
    );
    expect(screen.getByText('TODAY')).toBeTruthy();
  });

  it('expands week group via More (A4)', async () => {
    const user = userEvent.setup();
    const weekOld = Array.from({ length: 5 }, (_, i) => ({
      id: `w-${i}`,
      creator_id: 'c1',
      session_id: null,
      title: `Week ${i}`,
      provider_name: null,
      model: 'auto',
      updated_at: new Date(Date.now() - (3 + i) * 86400000).toISOString(),
    }));
    render(
      <AgentHistorySidebar
        threads={weekOld}
        activeThreadId={null}
        onSelectThread={() => {}}
        onOpenMenu={() => {}}
        onRenameCommit={() => {}}
        onRenameCancel={() => {}}
      />,
    );

    const more = screen.getByRole('button', { name: 'More' });
    expect(more).toBeTruthy();
    await user.click(more);
    expect(screen.getByText('Week 4')).toBeTruthy();
  });

  it('calls onOpenMenu from thread menu button (A5)', async () => {
    const user = userEvent.setup();
    const onOpenMenu = vi.fn();
    render(
      <AgentHistorySidebar
        threads={[
          {
            id: 'x',
            creator_id: 'c1',
            session_id: null,
            title: 'One',
            provider_name: null,
            model: 'auto',
            updated_at: new Date().toISOString(),
          },
        ]}
        activeThreadId={null}
        onSelectThread={() => {}}
        onOpenMenu={onOpenMenu}
        onRenameCommit={() => {}}
        onRenameCancel={() => {}}
      />,
    );
    await user.click(screen.getByLabelText('更多操作'));
    expect(onOpenMenu).toHaveBeenCalledWith('x', expect.any(HTMLElement));
  });
});
