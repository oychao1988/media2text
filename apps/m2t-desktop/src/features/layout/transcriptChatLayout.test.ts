import { beforeEach, describe, expect, it } from 'vitest';
import { transcriptChatRightW } from './layoutConstants';

describe('transcriptChatRightW', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'innerWidth', { value: 1200, configurable: true });
    document.documentElement.style.setProperty('--sidebar-w', '240px');
    document.documentElement.style.setProperty('--grip-w', '6px');
  });

  it('defaults agent column to half viewport when switching to transcript-chat', () => {
    expect(transcriptChatRightW(240)).toBe(600);
  });

  it('respects minimum center column width', () => {
    Object.defineProperty(window, 'innerWidth', { value: 900, configurable: true });
    expect(transcriptChatRightW(500)).toBe(280);
  });
});
