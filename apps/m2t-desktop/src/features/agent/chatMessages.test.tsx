import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { AGENT_GLOBAL_PROFILE } from './agentProfile';
import { ChatMessageAgent } from './ChatMessageAgent';
import { ChatMessageProcess } from './ChatMessageProcess';
import { ChatMessageUser } from './ChatMessageUser';
import * as toast from '../../lib/toast';

describe('ChatMessageUser', () => {
  it('renders Accio user bubble structure (A5)', () => {
    const { container } = render(
      <ChatMessageUser text="hello" createdAt="2026-06-07T14:31:11.000Z" />,
    );
    const article = container.querySelector('.chat-msg-user');
    expect(article).toBeTruthy();
    expect(container.querySelector('.chat-msg-bubble')).toBeTruthy();
    expect(container.querySelector('.chat-msg-actions')).toBeTruthy();
    expect(container.querySelector('.chat-msg-name')?.textContent).toBe('本地用户');
    expect(container.querySelector('.chat-msg-avatar.user')?.textContent).toBe('本');
    expect(screen.getByText('hello')).toBeTruthy();
  });
});

describe('ChatMessageProcess', () => {
  it('shows phase label while turn is active (A6)', () => {
    render(<ChatMessageProcess mode="active" phaseLabel="思考中…" />);
    expect(screen.getByText('思考中…')).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('shows completed duration and expandable thinking (A6)', async () => {
    const user = userEvent.setup();
    render(
      <ChatMessageProcess
        mode="completed"
        durationMs={12_000}
        thinkingText="step one"
      />,
    );
    expect(screen.getByText('已处理 12 秒')).toBeTruthy();
    const btn = screen.getByRole('button', { name: /已处理 12 秒/ });
    expect(btn).toHaveAttribute('aria-expanded', 'false');
    await user.click(btn);
    expect(btn).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('step one')).toBeTruthy();
  });

  it('hides chevron when no thinking text', () => {
    render(<ChatMessageProcess mode="completed" durationMs={3000} />);
    expect(screen.getByText('已处理 3 秒')).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('ChatMessageAgent', () => {
  it('renders full-width agent message with footer (A6)', () => {
    const { container } = render(
      <ChatMessageAgent
        profile={AGENT_GLOBAL_PROFILE}
        creators={[]}
        text="reply body"
        durationMs={5000}
        thinkingText="trace"
        createdAt="2026-06-07T14:31:42.000Z"
      />,
    );
    expect(container.querySelector('.chat-msg-agent')).toBeTruthy();
    expect(container.querySelector('.chat-msg-body')).toBeTruthy();
    expect(container.querySelector('.chat-msg-footer')).toBeTruthy();
    expect(screen.getByText('灵犀')).toBeTruthy();
    expect(screen.getByText('reply body')).toBeTruthy();
  });

  it('shows streaming phase without footer actions', () => {
    const { container } = render(
      <ChatMessageAgent
        profile={AGENT_GLOBAL_PROFILE}
        creators={[]}
        text="partial…"
        activePhaseLabel="生成回复…"
      />,
    );
    expect(screen.getByText('生成回复…')).toBeTruthy();
    expect(container.querySelector('.chat-msg-footer')).toBeNull();
  });

  it('shows reply duration in footer after thumbs down', () => {
    render(
      <ChatMessageAgent
        profile={AGENT_GLOBAL_PROFILE}
        creators={[]}
        text="done"
        durationMs={5000}
      />,
    );
    expect(screen.getByText('耗时 5 秒')).toBeTruthy();
  });

  it('copy footer shows toast', async () => {
    const user = userEvent.setup();
    const toastSpy = vi.spyOn(toast, 'showToast');
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    render(
      <ChatMessageAgent
        profile={AGENT_GLOBAL_PROFILE}
        creators={[]}
        text="copy me"
        durationMs={1000}
      />,
    );
    await user.click(screen.getByRole('button', { name: '复制' }));
    expect(writeText).toHaveBeenCalledWith('copy me');
    expect(toastSpy).toHaveBeenCalledWith('已复制', 'success');
    toastSpy.mockRestore();
    vi.unstubAllGlobals();
  });
});
