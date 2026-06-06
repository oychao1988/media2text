import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ChatMarkdown } from './ChatMarkdown';

describe('ChatMarkdown', () => {
  it('renders GFM tables as HTML tables', () => {
    const md = [
      '| 项目 | 状态 |',
      '|------|------|',
      '| 守护进程 | 🟢 运行中 |',
    ].join('\n');
    const { container } = render(<ChatMarkdown text={md} />);
    expect(container.querySelector('.agent-md-table')).toBeTruthy();
    expect(screen.getByText('项目')).toBeTruthy();
    expect(screen.getByText('🟢 运行中')).toBeTruthy();
  });
});
