import { describe, expect, it } from 'vitest';
import { positionAgentContextMenu } from './contextMenuPosition';

describe('positionAgentContextMenu', () => {
  it('anchors menu to the right of the trigger and clamps inside viewport', () => {
    Object.defineProperty(window, 'innerWidth', { value: 800, configurable: true });
    Object.defineProperty(window, 'innerHeight', { value: 600, configurable: true });

    const rect = {
      left: 720,
      right: 748,
      bottom: 120,
      top: 100,
      width: 28,
      height: 20,
      x: 720,
      y: 100,
      toJSON: () => ({}),
    } as DOMRect;

    const pos = positionAgentContextMenu(rect);
    expect(pos.x).toBe(600);
    expect(pos.y).toBe(124);
  });
});
