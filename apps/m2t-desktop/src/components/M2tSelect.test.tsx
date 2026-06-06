import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { M2tSelect } from './M2tSelect';

describe('M2tSelect', () => {
  it('opens menu and selects option', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <M2tSelect
        ariaLabel="主题"
        value="light"
        options={[
          { value: 'light', label: '亮色' },
          { value: 'dark', label: '暗色' },
        ]}
        onChange={onChange}
      />,
    );

    await user.click(screen.getByRole('button', { name: '主题' }));
    await user.click(screen.getByRole('option', { name: '暗色' }));
    expect(onChange).toHaveBeenCalledWith('dark');
  });
});
