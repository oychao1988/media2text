import { createRef } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AgentPanel, type AgentPanelHandle } from './AgentPanel';

vi.mock('../creators/CreatorsContext', () => ({
  useCreators: () => ({
    setSelectedId: vi.fn(),
    creators: [
      { id: 'creator-a', display_name: 'Creator A' },
      { id: 'creator-b', display_name: 'Creator B' },
    ],
  }),
}));

vi.mock('./useAgentThreads', () => ({
  useAgentThreads: () => ({
    threads: [
      {
        id: 't1',
        creator_id: 'creator-a',
        session_id: null,
        title: 'Thread A',
        provider_name: null,
        model: 'auto',
        updated_at: '2026-06-09T12:00:00Z',
      },
    ],
    createThread: vi.fn(),
    createGlobalThread: vi.fn(),
    renameThread: vi.fn(),
    deleteThread: vi.fn(),
    refresh: vi.fn(),
    applyThreadTitle: vi.fn(),
  }),
}));

vi.mock('./useM2tAgent', () => ({
  useM2tAgent: () => ({
    ready: true,
    status: 'ready',
    fatalError: null,
    messages: [],
    activeTurn: null,
    providers: [],
    threadModel: 'auto',
    patchThreadModel: vi.fn(),
    sendMessage: vi.fn(),
    retryMessage: vi.fn(),
  }),
}));

vi.mock('./useAgentHistoryResize', () => ({
  useAgentHistoryResize: () => ({
    onPointerDown: vi.fn(),
    onPointerMove: vi.fn(),
    onPointerUp: vi.fn(),
  }),
}));

describe('AgentPanel creator draft link (P0 #254)', () => {
  it('exposes openNewDraftForAgent via ref and focuses creator draft', async () => {
    const ref = createRef<AgentPanelHandle>();
    render(
      <AgentPanel
        ref={ref}
        creatorId="creator-a"
        sessionContext={{ sessionId: null }}
      />,
    );

    await waitFor(() => {
      expect(ref.current).toBeTruthy();
    });

    await act(async () => {
      ref.current!.openNewDraftForAgent('creator-b');
    });

    await waitFor(() => {
      expect(screen.getByText('Creator B')).toBeTruthy();
    });
  });

  it('reuses same-agent empty draft on repeated openNewDraftForAgent calls', async () => {
    const ref = createRef<AgentPanelHandle>();
    render(
      <AgentPanel
        ref={ref}
        creatorId="creator-a"
        sessionContext={{ sessionId: null }}
      />,
    );

    await waitFor(() => expect(ref.current).toBeTruthy());

    await act(async () => {
      ref.current!.openNewDraftForAgent('creator-b');
    });
    await act(async () => {
      ref.current!.openNewDraftForAgent('creator-b');
    });

    await waitFor(() => {
      const tabs = document.querySelectorAll('[role="tab"]');
      const draftTabs = Array.from(tabs).filter((t) => t.textContent?.includes('新对话'));
      expect(draftTabs.length).toBeLessThanOrEqual(2);
    });
  });
});
