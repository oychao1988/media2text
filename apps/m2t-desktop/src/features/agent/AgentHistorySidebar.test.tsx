import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AgentHistorySidebar } from './AgentHistorySidebar';
import type { ThreadRow } from './types';

const creators = [
  { id: 'c1', display_name: '博主甲' },
  { id: 'c2', display_name: '博主乙' },
];

const defaultProps = {
  creators,
  onSelectThread: () => {},
  onOpenMenu: () => {},
  onRenameCommit: () => {},
  onRenameCancel: () => {},
  onBatchDeleteRequest: () => {},
};

describe('AgentHistorySidebar', () => {
  it('filters threads by search', async () => {
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
        {...defaultProps}
      />,
    );

    expect(screen.getByText('Market recap')).toBeTruthy();
    await user.type(screen.getByPlaceholderText('搜索 Agent…'), 'market');
    expect(screen.queryByText('Other chat')).toBeNull();
  });

  it('groups threads by agent with global first', () => {
    const threads: ThreadRow[] = [
      {
        id: 'g1',
        creator_id: null,
        session_id: null,
        title: 'Global chat',
        provider_name: null,
        model: 'auto',
        updated_at: new Date().toISOString(),
      },
      {
        id: 'c1t',
        creator_id: 'c1',
        session_id: null,
        title: 'Creator chat',
        provider_name: null,
        model: 'auto',
        updated_at: new Date().toISOString(),
      },
    ];
    render(
      <AgentHistorySidebar
        threads={threads}
        activeThreadId={null}
        {...defaultProps}
      />,
    );

    expect(screen.getByText('灵犀')).toBeTruthy();
    expect(screen.getByText('博主甲')).toBeTruthy();
    expect(screen.getByText('Global chat')).toBeTruthy();
  });

  it('shows empty state when no threads', () => {
    render(
      <AgentHistorySidebar threads={[]} activeThreadId={null} {...defaultProps} />,
    );
    expect(screen.getByText('暂无会话')).toBeTruthy();
  });

  it('requests batch delete for agent group', async () => {
    const user = userEvent.setup();
    const onBatchDeleteRequest = vi.fn();
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
        {...defaultProps}
        onBatchDeleteRequest={onBatchDeleteRequest}
      />,
    );
    await user.click(screen.getByLabelText('删除 博主甲 下全部会话'));
    expect(onBatchDeleteRequest).toHaveBeenCalledWith('c1', ['x']);
  });
});
