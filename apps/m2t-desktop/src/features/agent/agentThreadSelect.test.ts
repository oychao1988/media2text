import { describe, expect, it, vi } from 'vitest';
import { shouldNotifyCreatorMismatch } from './agentThreadSelect';

describe('creator mismatch (D3)', () => {
  it('detects when thread creator differs from selected creator', () => {
    expect(shouldNotifyCreatorMismatch('c-other', 'c-selected')).toBe(true);
    expect(shouldNotifyCreatorMismatch('c-selected', 'c-selected')).toBe(false);
    expect(shouldNotifyCreatorMismatch('c-other', null)).toBe(false);
  });

  it('would show toast with switch action when mismatch', () => {
    const onSwitch = vi.fn();
    const threadCreatorId = 'c-other';
    const selectedId = 'c-selected';
    if (shouldNotifyCreatorMismatch(threadCreatorId, selectedId)) {
      onSwitch();
    }
    expect(onSwitch).toHaveBeenCalledOnce();
  });
});
