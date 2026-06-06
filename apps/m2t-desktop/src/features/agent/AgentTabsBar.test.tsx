import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AgentTabsBar } from './AgentTabsBar';
import type { ThreadRow } from './types';

const threads: ThreadRow[] = [
  {
    id: 't1',
    creator_id: 'c1',
    session_id: null,
    title: 'Thread One',
    provider_name: null,
    model: 'auto',
    updated_at: '2026-06-06T12:00:00Z',
  },
  {
    id: 't2',
    creator_id: 'c1',
    session_id: null,
    title: 'Thread Two',
    provider_name: null,
    model: 'auto',
    updated_at: '2026-06-05T12:00:00Z',
  },
];

describe('AgentTabsBar', () => {
  it('renders tabs with close buttons and new/history actions (A2/A3)', async () => {
    const user = userEvent.setup();
    const onCloseTab = vi.fn();
    const onNewThread = vi.fn();
    const onToggleHistory = vi.fn();

    render(
      <AgentTabsBar
        tabIds={['t1', 't2']}
        threads={threads}
        activeThreadId="t1"
        historyCollapsed={false}
        onSelectTab={() => {}}
        onCloseTab={onCloseTab}
        onNewThread={onNewThread}
        onToggleHistory={onToggleHistory}
      />,
    );

    expect(screen.getByRole('tab', { name: 'Thread One' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getAllByLabelText('关闭页签')).toHaveLength(2);
    await user.click(screen.getAllByLabelText('关闭页签')[0]);
    expect(onCloseTab).toHaveBeenCalledWith('t1');

    await user.click(screen.getByLabelText('新建 Agent'));
    expect(onNewThread).toHaveBeenCalledOnce();

    await user.click(screen.getByLabelText('隐藏历史会话'));
    expect(onToggleHistory).toHaveBeenCalledOnce();
  });
});
