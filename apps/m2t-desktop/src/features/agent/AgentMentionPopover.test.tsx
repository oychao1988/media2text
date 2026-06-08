import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AgentMentionPopover } from './AgentMentionPopover';
import type { MentionDocumentRow } from './mentionDocuments';

const rows: MentionDocumentRow[] = [
  {
    rowKey: '1',
    creatorId: 'c1',
    creatorName: '博主A',
    sessionKind: 'live',
    itemId: 's1',
    docType: 'transcript',
    path: 'a.json',
    label: '博主A · 直播 · 转写',
    searchText: '博主a',
  },
];

describe('AgentMentionPopover', () => {
  it('shows empty state when no rows', () => {
    render(
      <AgentMentionPopover
        open
        rows={[]}
        loading={false}
        activeIndex={0}
        onSelect={vi.fn()}
        onActiveIndexChange={vi.fn()}
      />,
    );
    expect(screen.getByText('无匹配文档')).toBeTruthy();
  });

  it('calls onSelect when item clicked', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <AgentMentionPopover
        open
        rows={rows}
        loading={false}
        activeIndex={0}
        onSelect={onSelect}
        onActiveIndexChange={vi.fn()}
      />,
    );
    await user.click(screen.getByRole('option', { name: rows[0]!.label }));
    expect(onSelect).toHaveBeenCalledWith(rows[0]);
  });
});
