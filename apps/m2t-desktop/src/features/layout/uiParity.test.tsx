import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { AgentComposer } from '../agent/AgentComposer';
import { ViewPlayback } from '../history/ViewPlayback';
import { DesktopLayoutPresets } from './DesktopLayoutPresets';
import { initLayoutStore, useLayoutStore } from './useLayoutStore';
import { LAYOUT_STORAGE_KEY, loadLayout } from './layoutConstants';

const layoutCss = readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), '../../styles/layout.css'),
  'utf-8',
);

function LayoutProbe() {
  const { centerView } = useLayoutStore();
  return <span data-testid="center-view">{centerView}</span>;
}

describe('ui parity CSS', () => {
  it('includes agent-pane and row-resize styles', () => {
    expect(layoutCss).toContain('.agent-pane');
    expect(layoutCss).toContain('.row-resize');
    expect(layoutCss).not.toContain('.history-layout');
    expect(layoutCss).not.toContain('.right-agent-shell');
    expect(layoutCss).not.toContain('.agent-msg--');
  });

  it('uses bottom-center toast pattern', () => {
    expect(layoutCss).toMatch(/\.toast\.show[\s\S]*translateX\(-50%\)/);
  });

  it('clips left panel overflow while toggling', () => {
    expect(layoutCss).toContain('.app.panel-toggling .creator-list');
    expect(layoutCss).toMatch(/\.app\.panel-toggling[\s\S]*overflow:\s*hidden/);
  });

  it('defines global scrollbar styling', () => {
    expect(layoutCss).toMatch(/\*::-webkit-scrollbar-thumb[\s\S]*border-radius:\s*999px/);
    expect(layoutCss).toContain('scrollbar-color: var(--scrollbar-thumb)');
  });

  it('includes desktop layout preset styles', () => {
    expect(layoutCss).toContain('.desktop-layout-transcript');
    expect(layoutCss).toContain('.transcript-center-slot');
    expect(layoutCss).toContain('.layout-preset-btn');
    expect(layoutCss).toMatch(
      /\.app\.desktop-layout-transcript:not\(\.right-collapsed\)[\s\S]*var\(--right-w\)/,
    );
  });
});

describe('AgentComposer structure', () => {
  it('renders Cursor-style composer with send svg', () => {
    render(
      <AgentComposer
        ready
        model="auto"
        providerModels={[]}
        onModelChange={() => {}}
        onSend={() => {}}
      />,
    );
    expect(document.getElementById('agent-form')).toBeTruthy();
    expect(document.getElementById('agent-input')).toBeTruthy();
    expect(document.getElementById('btn-agent-send')).toBeTruthy();
    expect(screen.getByRole('button', { name: '发送' })).toBeTruthy();
    expect(screen.getByLabelText('Agent 模型')).toBeTruthy();
    expect(screen.getByText('∞')).toBeTruthy();
    expect(screen.getByText('Agent')).toBeTruthy();
  });
});

describe('DesktopLayoutPresets', () => {
  it('sets rightW to half viewport when selecting transcript-chat preset', async () => {
    localStorage.clear();
    initLayoutStore();
    Object.defineProperty(window, 'innerWidth', { value: 1200, configurable: true });
    document.documentElement.style.setProperty('--sidebar-w', '240px');
    document.documentElement.style.setProperty('--grip-w', '6px');
    document.body.innerHTML = '<div id="app" class="app"></div>';
    const user = userEvent.setup();

    render(<DesktopLayoutPresets />);
    await user.click(screen.getByRole('button', { name: '博主 · 转写 · 对话' }));

    expect(loadLayout().rightW).toBe(600);
    expect(document.documentElement.style.getPropertyValue('--right-w')).toBe('600px');
  });
});

describe('ViewPlayback routing', () => {
  it('back button returns to history view in layout store', async () => {
    initLayoutStore();
    const user = userEvent.setup();

    const session = {
      session_id: 's1',
      creator_id: 'c1',
      started_at: '2026-06-02T21:04:00Z',
      ended_at: '2026-06-02T23:22:00Z',
      status: 'completed',
      local_path: null,
      temp_path: null,
      media_path: '/data/live/x.mp4',
      pipeline_mode: null,
      transcribe_status: null,
      cloud_upload_status: null,
      has_transcript: true,
      has_summary: false,
      media_available: false,
      transcript_path: null,
      summary_path: null,
    };

    render(
      <>
        <LayoutProbe />
        <ViewPlayback active creatorName="测试博主" session={session} />
      </>,
    );

    await user.click(screen.getByRole('button', { name: /返回列表/ }));
    expect(screen.getByTestId('center-view')).toHaveTextContent('history');
  });
});
