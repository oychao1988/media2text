import { describe, expect, it, vi } from 'vitest';
import {
  isGlobalThread,
  shouldNotifyCreatorMismatch,
} from './agentThreadSelect';

describe('creator mismatch (M5a)', () => {
  it('detects when thread creator differs from selected creator', () => {
    expect(shouldNotifyCreatorMismatch('c-other', 'c-selected')).toBe(true);
    expect(shouldNotifyCreatorMismatch('c-selected', 'c-selected')).toBe(false);
    expect(shouldNotifyCreatorMismatch('c-other', null)).toBe(false);
    expect(shouldNotifyCreatorMismatch(null, 'c-selected')).toBe(false);
  });

  it('does not block composer for global threads', () => {
    expect(isGlobalThread(null)).toBe(true);
    expect(isGlobalThread('')).toBe(true);
    expect(isGlobalThread('c1')).toBe(false);
  });

  it('would show toast with switch action when mismatch on select', () => {
    const onSwitch = vi.fn();
    const threadCreatorId = 'c-other';
    const selectedId = 'c-selected';
    if (shouldNotifyCreatorMismatch(threadCreatorId, selectedId)) {
      onSwitch();
    }
    expect(onSwitch).toHaveBeenCalledOnce();
  });
});
