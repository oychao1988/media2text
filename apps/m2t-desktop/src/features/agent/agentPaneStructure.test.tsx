import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AgentPanel } from './AgentPanel';

vi.mock('../creators/CreatorsContext', () => ({
  useCreators: () => ({
    setSelectedId: vi.fn(),
    creators: [{ id: 'c1', display_name: 'Test Creator' }],
  }),
}));

vi.mock('./useAgentThreads', () => ({
  useAgentThreads: () => ({
    threads: [
      {
        id: 't1',
        creator_id: 'c1',
        session_id: null,
        title: 'Test',
        provider_name: null,
        model: 'auto',
        updated_at: '2026-06-06T12:00:00Z',
      },
    ],
    createThread: vi.fn(),
    createGlobalThread: vi.fn(),
    renameThread: vi.fn(),
    deleteThread: vi.fn(),
  }),
}));

vi.mock('./useM2tAgent', () => ({
  useM2tAgent: () => ({
    ready: false,
    status: 'starting',
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

const layoutCss = readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), '../../styles/layout.css'),
  'utf-8',
);

describe('AgentPanel structure (A1/A7)', () => {
  it('renders tabs bar without legacy agent-header', () => {
    render(
      <AgentPanel
        creatorId="c1"
        sessionContext={{ sessionId: null }}
      />,
    );
    expect(document.getElementById('agent-tabs-bar')).toBeTruthy();
    expect(document.querySelector('.agent-header')).toBeNull();
    expect(document.querySelector('.model-pill')).toBeNull();
    expect(screen.getByLabelText('Agent')).toBeTruthy();
  });

  it('includes agent multi-tab CSS tokens', () => {
    expect(layoutCss).toContain('.agent-tabs-bar');
    expect(layoutCss).toContain('.agent-history');
    expect(layoutCss).toContain('.agent-header-icon-btn');
    expect(layoutCss).toContain('.agent-pane.agent-history-collapsed');
    expect(layoutCss).toContain('.agent-tab-avatar');
    expect(layoutCss).toContain('.agent-thread-group-head');
    expect(layoutCss).toContain('.toast-action');
  });
});
