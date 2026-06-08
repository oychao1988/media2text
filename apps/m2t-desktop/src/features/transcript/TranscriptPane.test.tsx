import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { TranscriptPane } from './TranscriptPane';

vi.mock('../../lib/api', () => ({
  apiGet: vi.fn(async () => ({ segments: [], text: '' })),
  apiPost: vi.fn(),
  buildWsUrl: vi.fn(async () => 'ws://test'),
  mediaUrl: vi.fn(async (p: string) => p),
}));

vi.mock('./TranscriptSessionSelect', () => ({
  TranscriptSessionSelect: () => null,
}));

describe('TranscriptPane onTabChange', () => {
  it('notifies parent when summary tab is selected', async () => {
    const user = userEvent.setup();
    const onTabChange = vi.fn();
    render(
      <TranscriptPane
        sessionId={null}
        summaryPath={null}
        onTabChange={onTabChange}
      />,
    );

    expect(onTabChange).toHaveBeenCalledWith('transcript');

    onTabChange.mockClear();
    await user.click(screen.getByRole('tab', { name: '摘要' }));
    expect(onTabChange).toHaveBeenCalledWith('summary');
  });
});
