import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AgentComposer } from './AgentComposer';

describe('AgentComposer (M5a mismatch)', () => {
  it('disables input and send when blocked', () => {
    render(
      <AgentComposer
        ready
        blocked
        model="auto"
        providerModels={[]}
        onModelChange={() => {}}
        onSend={vi.fn()}
      />,
    );

    const input = screen.getByLabelText('Agent 输入');
    expect(input).toHaveProperty('disabled', true);
    expect(input.getAttribute('placeholder')).toBe('博主不一致，无法发送…');
    expect(screen.getByLabelText('发送')).toHaveProperty('disabled', true);
  });

  it('allows send on global thread when ready and not blocked', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(
      <AgentComposer
        ready
        blocked={false}
        model="auto"
        providerModels={[]}
        onModelChange={() => {}}
        onSend={onSend}
      />,
    );

    const input = screen.getByLabelText('Agent 输入');
    await user.type(input, 'hello');
    await user.click(screen.getByLabelText('发送'));
    expect(onSend).toHaveBeenCalledWith('hello');
  });
});
