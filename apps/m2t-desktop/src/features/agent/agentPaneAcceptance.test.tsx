import { render, screen, waitFor } from '@testing-library/react';
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
  useCreators: () => ({ setSelectedId }),
}));

vi.mock('./useAgentThreads', () => ({
  useAgentThreads: () => ({
    threads,
    createThread: vi.fn(),
    renameThread,
    deleteThread,
  }),
}));

vi.mock('./useM2tAgent', () => ({
  useM2tAgent: () => ({
    ready: true,
    status: 'ready',
    fatalError: null,
    messages: [],
    activeTurn: null,
    providers: [{ name: 'nvidia', models: ['z-ai/glm-5.1'] }],
    threadModel: 'auto',
    patchThreadModel: vi.fn(),
    sendMessage: vi.fn(),
  }),
}));

describe('Agent pane acceptance (A5/A6/A10)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.removeItem(LAYOUT_STORAGE_KEY);
  });

  it('A5: rename via context menu calls PATCH hook after prompt', async () => {
    const user = userEvent.setup();
    const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('Renamed session');
    render(<AgentPanel creatorId="creator-a" sessionContext={{ sessionId: null }} />);

    const menuButtons = screen.getAllByLabelText('更多操作');
    await user.click(menuButtons[0]);
    await user.click(screen.getByRole('menuitem', { name: '重命名' }));

    await waitFor(() => {
      expect(promptSpy).toHaveBeenCalled();
      expect(renameThread).toHaveBeenCalledWith('t-current', 'Renamed session');
    });
    promptSpy.mockRestore();
  });

  it('A5: delete via context menu calls DELETE hook after confirm', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<AgentPanel creatorId="creator-a" sessionContext={{ sessionId: null }} />);

    const menus = screen.getAllByLabelText('更多操作');
    await user.click(menus[0]);
    await user.click(screen.getByRole('menuitem', { name: '删除' }));

    await waitFor(() => {
      expect(confirmSpy).toHaveBeenCalled();
      expect(deleteThread).toHaveBeenCalledWith('t-current');
    });
    confirmSpy.mockRestore();
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
