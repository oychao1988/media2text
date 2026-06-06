import type { DesktopLayoutPreset } from './layoutConstants';

/** CSS classes on `#app` for the active desktop layout preset (first paint + store sync). */
export function layoutPresetAppClass(preset: DesktopLayoutPreset): string {
  if (preset === 'transcript-chat') return 'desktop-layout-transcript';
  if (preset === 'chat-only') return 'desktop-layout-chat-only desktop-layout-chat';
  return 'desktop-layout-full';
}
