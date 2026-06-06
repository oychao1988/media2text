import { beforeEach, describe, expect, it } from 'vitest';
import {
  DEFAULT_LAYOUT,
  loadLayout,
  saveLayout,
  type LayoutPersist,
} from './layoutConstants';

describe('desktopLayoutPreset persist', () => {
  beforeEach(() => localStorage.clear());

  it('round-trips desktopLayoutPreset and agentHistoryW', () => {
    const layout: LayoutPersist = {
      ...DEFAULT_LAYOUT,
      desktopLayoutPreset: 'transcript-chat',
      agentHistoryW: 220,
    };
    saveLayout(layout);
    expect(loadLayout().desktopLayoutPreset).toBe('transcript-chat');
    expect(loadLayout().agentHistoryW).toBe(220);
  });

  it('defaults invalid preset to full', () => {
    localStorage.setItem(
      'm2t-desktop-layout',
      JSON.stringify({ ...DEFAULT_LAYOUT, desktopLayoutPreset: 'invalid' }),
    );
    expect(loadLayout().desktopLayoutPreset).toBe('full');
  });
});
