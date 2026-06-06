import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AgentTabsBar } from './AgentTabsBar';
import { createDraftTab, tabEntryKey } from './useAgentTabs';
import type { ThreadRow } from './types';

const creators = [
  { id: 'c1', display_name: '博主甲' },
];

const threads: ThreadRow[] = [
  {
    id: 't1',
    creator_id: null,
    session_id: null,
    title: 'Global Thread',
    provider_name: null,
    model: 'auto',
    updated_at: '2026-06-06T12:00:00Z',
  },
  {
    id: 't2',
    creator_id: 'c1',
    session_id: null,
    title: 'Creator Thread',
    provider_name: null,
    model: 'auto',
    updated_at: '2026-06-05T12:00:00Z',
  },
];

describe('AgentTabsBar', () => {
  it('renders tab avatars for global and creator threads', () => {
    render(
      <AgentTabsBar
        tabEntries={[
          { kind: 'thread', threadId: 't1' },
          { kind: 'thread', threadId: 't2' },
        ]}
        threads={threads}
        creators={creators}
        activeTabKey="thread:t1"
        historyCollapsed={false}
        onSelectTab={() => {}}
        onCloseTab={() => {}}
        onNewDraft={() => {}}
        onToggleHistory={() => {}}
      />,
    );

    const avatars = document.querySelectorAll('.agent-tab-avatar');
    expect(avatars).toHaveLength(2);
    expect(avatars[0]?.classList.contains('global')).toBe(true);
    expect(avatars[0]?.textContent).toBe('灵');
    expect(avatars[1]?.textContent).toBe('博主');
  });

  it('renders draft tab with agent avatar', () => {
    const draft = createDraftTab('c1');
    render(
      <AgentTabsBar
        tabEntries={[draft]}
        threads={threads}
        creators={creators}
        activeTabKey={tabEntryKey(draft)}
        historyCollapsed={false}
        onSelectTab={() => {}}
        onCloseTab={() => {}}
        onNewDraft={() => {}}
        onToggleHistory={() => {}}
      />,
    );
    expect(screen.getByText('新对话')).toBeTruthy();
    expect(document.querySelector('.agent-tab-avatar')?.textContent).toBe('博主');
  });

  it('calls onNewDraft from + button', async () => {
    const user = userEvent.setup();
    const onNewDraft = vi.fn();
    render(
      <AgentTabsBar
        tabEntries={[]}
        threads={threads}
        creators={creators}
        activeTabKey={null}
        historyCollapsed={false}
        onSelectTab={() => {}}
        onCloseTab={() => {}}
        onNewDraft={onNewDraft}
        onToggleHistory={() => {}}
      />,
    );
    await user.click(screen.getByLabelText('新建 Agent'));
    expect(onNewDraft).toHaveBeenCalledOnce();
  });
});
