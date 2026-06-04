import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { StatusLight as StatusLightKind } from '../../lib/types';
import { StatusLight } from './StatusLight';

const cases: Array<[StatusLightKind, string, string]> = [
  ['green', '录制中', '录'],
  ['red', '在播未录', '播'],
  ['yellow', '收尾中', '收'],
  ['gray', '离线', '离'],
];

describe('StatusLight', () => {
  it.each(cases)('renders %s with aria-label and abbr', (light, label, abbr) => {
    render(<StatusLight light={light} abbr={abbr} />);
    const el = screen.getByRole('img', { name: label });
    expect(el).toHaveClass('light', light);
    expect(el).toHaveAttribute('data-abbr', abbr);
    expect(el).toHaveAttribute('title', label);
  });

  it('falls back abbr to first aria-label char when omitted', () => {
    render(<StatusLight light="green" />);
    expect(screen.getByRole('img', { name: '录制中' })).toHaveAttribute('data-abbr', '录');
  });
});
