import { describe, expect, it } from 'vitest';
import { closeAgentTab, pushAgentTab } from './useAgentTabs';

describe('useAgentTabs helpers', () => {
  it('caps at 5 tabs dropping oldest', () => {
    let ids = ['a', 'b', 'c', 'd', 'e'];
    ids = pushAgentTab(ids, 'f');
    expect(ids).toEqual(['b', 'c', 'd', 'e', 'f']);
  });

  it('close tab does not delete thread id from API', () => {
    const { tabIds, activeId } = closeAgentTab(['a', 'b'], 'a', 'a');
    expect(tabIds).toEqual(['b']);
    expect(activeId).toBe('b');
  });
});
