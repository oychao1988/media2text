import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AgentTabsBar } from './AgentTabsBar';
import { createDraftTab, tabEntryKey } from './useAgentTabs';
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
    const onNewDraft = vi.fn();
    const onToggleHistory = vi.fn();

    render(
      <AgentTabsBar
        tabEntries={[
          { kind: 'thread', threadId: 't1' },
          { kind: 'thread', threadId: 't2' },
        ]}
        threads={threads}
        creators={[]}
        activeTabKey="thread:t1"
        historyCollapsed={false}
        onSelectTab={() => {}}
        onCloseTab={onCloseTab}
        onNewDraft={onNewDraft}
        onToggleHistory={onToggleHistory}
      />,
    );

    expect(screen.getByRole('tab', { name: 'Thread One' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getAllByLabelText('关闭页签')).toHaveLength(2);
    await user.click(screen.getAllByLabelText('关闭页签')[0]);
    expect(onCloseTab).toHaveBeenCalledWith('thread:t1');

    await user.click(screen.getByLabelText('新建 Agent'));
    expect(onNewDraft).toHaveBeenCalledOnce();

    await user.click(screen.getByLabelText('隐藏历史会话'));
    expect(onToggleHistory).toHaveBeenCalledOnce();
  });

  it('renders draft tab label', () => {
    const draft = createDraftTab('global');
    render(
      <AgentTabsBar
        tabEntries={[draft]}
        threads={threads}
        creators={[]}
        activeTabKey={tabEntryKey(draft)}
        historyCollapsed={false}
        onSelectTab={() => {}}
        onCloseTab={() => {}}
        onNewDraft={() => {}}
        onToggleHistory={() => {}}
      />,
    );
    expect(screen.getByText('新对话')).toBeTruthy();
  });
});
