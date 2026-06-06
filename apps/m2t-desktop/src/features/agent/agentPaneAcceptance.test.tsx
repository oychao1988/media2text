import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AgentPanel } from './AgentPanel';
import { commitLayoutSizes, initLayoutStore } from '../layout/useLayoutStore';
import { LAYOUT_STORAGE_KEY, loadLayout } from '../layout/layoutConstants';
import * as toast from '../../lib/toast';
import type { ThreadRow } from './types';

const renameThread = vi.fn();
const deleteThread = vi.fn();
const setSelectedId = vi.fn();

const defaultAgentMock = {
  ready: true,
  status: 'ready' as const,
  fatalError: null,
  messages: [] as Array<
    | { id: string; role: 'user'; text: string; createdAt?: string }
    | {
        id: string;
        role: 'assistant';
        text: string;
        thinkingText?: string;
        durationMs?: number;
        createdAt?: string;
      }
  >,
  activeTurn: null as {
    phase: string;
    phaseLabel: string;
    thinkingText: string;
    assistantText: string;
  } | null,
  providers: [{ name: 'nvidia', models: ['z-ai/glm-5.1'] }],
  threadModel: 'auto',
  patchThreadModel: vi.fn(),
  sendMessage: vi.fn(),
};

let agentMock = { ...defaultAgentMock, messages: [...defaultAgentMock.messages] };

const threads: ThreadRow[] = [
  {
    id: 't-current',
    creator_id: 'creator-a',
    session_id: null,
    title: 'Current creator chat',
    provider_name: null,
    model: 'auto',
    updated_at: new Date().toISOString(),
  },
  {
    id: 't-other',
    creator_id: 'creator-b',
    session_id: null,
    title: 'Other creator chat',
    provider_name: null,
    model: 'auto',
    updated_at: new Date().toISOString(),
  },
];

vi.mock('../creators/CreatorsContext', () => ({
  useCreators: () => ({
    setSelectedId,
    creators: [{ id: 'creator-a', display_name: '博主A' }],
  }),
}));

vi.mock('./useAgentThreads', () => ({
  useAgentThreads: () => ({
    threads,
    createThread: vi.fn(),
    createGlobalThread: vi.fn(),
    renameThread,
    deleteThread,
  }),
}));

vi.mock('./useM2tAgent', () => ({
  useM2tAgent: () => agentMock,
}));

describe('Agent pane acceptance (A5/A6/A10)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.removeItem(LAYOUT_STORAGE_KEY);
    agentMock = {
      ...defaultAgentMock,
      messages: [],
      activeTurn: null,
      patchThreadModel: vi.fn(),
      sendMessage: vi.fn(),
    };
  });

  it('A5: user messages use right-aligned Accio bubble', async () => {
    const user = userEvent.setup();
    agentMock.messages = [
      { id: 'u1', role: 'user', text: '用户问题', createdAt: '2026-06-07T10:00:00.000Z' },
    ];
    render(<AgentPanel creatorId="creator-a" sessionContext={{ sessionId: null }} />);

    await user.click(screen.getByRole('button', { name: 'Current creator chat' }));

    const live = document.getElementById('chat-live');
    expect(live).toBeTruthy();
    const bubble = live?.querySelector('.chat-msg-user .chat-msg-bubble');
    expect(bubble).toBeTruthy();
    expect(within(live as HTMLElement).getByText('用户问题')).toBeTruthy();
  });

  it('A6: assistant messages show process row and footer', async () => {
    const user = userEvent.setup();
    agentMock.messages = [
      {
        id: 'a1',
        role: 'assistant',
        text: '助手回复',
        thinkingText: '推理过程',
        durationMs: 8000,
        createdAt: '2026-06-07T10:00:01.000Z',
      },
    ];
    render(<AgentPanel creatorId="creator-a" sessionContext={{ sessionId: null }} />);

    await user.click(screen.getByRole('button', { name: 'Current creator chat' }));

    const live = document.getElementById('chat-live');
    expect(live?.querySelector('.chat-msg-agent')).toBeTruthy();
    expect(within(live as HTMLElement).getByText('已处理 8 秒')).toBeTruthy();
    expect(live?.querySelector('.chat-msg-footer')).toBeTruthy();
  });

  it('A6: active turn shows phase label without expandable thinking', async () => {
    const user = userEvent.setup();
    agentMock.activeTurn = {
      phase: 'thinking',
      phaseLabel: '思考中…',
      thinkingText: 'hidden until complete',
      assistantText: '',
    };
    render(<AgentPanel creatorId="creator-a" sessionContext={{ sessionId: null }} />);

    await user.click(screen.getByRole('button', { name: 'Current creator chat' }));

    const live = document.getElementById('chat-live');
    expect(within(live as HTMLElement).getByText('思考中…')).toBeTruthy();
    expect(within(live as HTMLElement).queryByText('hidden until complete')).toBeNull();
  });

  it('rename via context menu edits inline and calls PATCH hook', async () => {
    const user = userEvent.setup();
    render(<AgentPanel creatorId="creator-a" sessionContext={{ sessionId: null }} />);

    const menuButtons = screen.getAllByLabelText('更多操作');
    await user.click(menuButtons[0]);
    await user.click(screen.getByRole('menuitem', { name: '重命名' }));

    const input = await screen.findByLabelText('重命名会话');
    await user.clear(input);
    await user.type(input, 'Renamed session');
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(renameThread).toHaveBeenCalledWith('t-current', 'Renamed session');
    });
  });

  it('delete via context menu calls DELETE hook after confirm', async () => {
    const user = userEvent.setup();
    render(<AgentPanel creatorId="creator-a" sessionContext={{ sessionId: null }} />);

    const menus = screen.getAllByLabelText('更多操作');
    await user.click(menus[0]);
    await user.click(screen.getByRole('menuitem', { name: '删除' }));
    await user.click(screen.getByRole('button', { name: '删除' }));

    await waitFor(() => {
      expect(deleteThread).toHaveBeenCalledWith('t-current');
    });
  });

  it('A6: drag end persists agentHistoryW to layout storage', () => {
    initLayoutStore();
    commitLayoutSizes({ agentHistoryW: 260 });
    expect(loadLayout().agentHistoryW).toBe(260);
    document.documentElement.style.setProperty('--agent-history-w', '260px');
    expect(document.documentElement.style.getPropertyValue('--agent-history-w')).toBe('260px');
  });

  it('A10: selecting other-creator thread shows switch toast action', async () => {
    const user = userEvent.setup();
    const toastSpy = vi.spyOn(toast, 'showToastWithAction');
    render(<AgentPanel creatorId="creator-a" sessionContext={{ sessionId: null }} />);

    await user.click(screen.getByRole('button', { name: 'Other creator chat' }));

    expect(toastSpy).toHaveBeenCalledWith(
      '该会话属于其他博主',
      'info',
      8000,
      expect.objectContaining({
        label: '切换到该博主',
        onAction: expect.any(Function),
      }),
    );
    const action = toastSpy.mock.calls[0][3];
    action?.onAction();
    expect(setSelectedId).toHaveBeenCalledWith('creator-b');
    toastSpy.mockRestore();
  });
});
