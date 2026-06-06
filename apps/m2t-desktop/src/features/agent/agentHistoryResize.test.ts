import { describe, expect, it } from 'vitest';
import { clamp, SIZE_LIMITS } from '../layout/layoutConstants';

/** Mirrors useAgentHistoryResize drag math (A6). */
function historyWidthAfterDrag(startW: number, dx: number): number {
  return clamp(startW - dx, SIZE_LIMITS.agentHistory.min, SIZE_LIMITS.agentHistory.max);
}

describe('agent history resize limits (A6)', () => {
  it('clamps to 140–340px', () => {
    expect(SIZE_LIMITS.agentHistory).toEqual({ min: 140, max: 340 });
    expect(historyWidthAfterDrag(200, 0)).toBe(200);
    expect(historyWidthAfterDrag(200, 200)).toBe(140);
    expect(historyWidthAfterDrag(200, -200)).toBe(340);
  });
});
