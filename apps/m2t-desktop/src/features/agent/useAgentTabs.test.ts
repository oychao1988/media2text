import { describe, expect, it } from 'vitest';
import { activateAgentTab, closeAgentTab, pushAgentTab } from './useAgentTabs';

describe('useAgentTabs helpers', () => {
  it('caps at 5 tabs dropping oldest', () => {
    let ids = ['a', 'b', 'c', 'd', 'e'];
    ids = pushAgentTab(ids, 'f');
    expect(ids).toEqual(['b', 'c', 'd', 'e', 'f']);
  });

  it('activateAgentTab keeps order when reorder is false', () => {
    expect(activateAgentTab(['a', 'b', 'c'], 'a', { reorder: false })).toEqual(['a', 'b', 'c']);
  });

  it('activateAgentTab moves tab to end by default', () => {
    expect(activateAgentTab(['a', 'b', 'c'], 'a')).toEqual(['b', 'c', 'a']);
  });

  it('close tab does not delete thread id from API', () => {
    const { tabIds, activeId } = closeAgentTab(['a', 'b'], 'a', 'a');
    expect(tabIds).toEqual(['b']);
    expect(activeId).toBe('b');
  });
});
