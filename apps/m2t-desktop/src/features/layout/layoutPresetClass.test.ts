import { describe, expect, it } from 'vitest';
import { layoutPresetAppClass } from './layoutPresetClass';

describe('layoutPresetAppClass', () => {
  it('maps presets to app shell classes', () => {
    expect(layoutPresetAppClass('full')).toBe('desktop-layout-full');
    expect(layoutPresetAppClass('transcript-chat')).toBe('desktop-layout-transcript');
    expect(layoutPresetAppClass('chat-only')).toBe('desktop-layout-chat-only desktop-layout-chat');
  });
});
