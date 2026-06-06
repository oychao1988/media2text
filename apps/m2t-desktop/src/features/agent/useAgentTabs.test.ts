import { describe, expect, it } from 'vitest';
import {
  activateAgentTabEntry,
  closeAgentTabEntry,
  createDraftTab,
  promoteDraftTab,
  pushAgentTabEntry,
  tabEntryKey,
} from './useAgentTabs';

describe('useAgentTabs draft model', () => {
  it('creates draft tab with global agent by default', () => {
    const draft = createDraftTab();
    expect(draft.kind).toBe('draft');
    expect(draft.agentId).toBe('global');
    expect(tabEntryKey(draft)).toMatch(/^draft:/);
  });

  it('promotes draft to thread tab', () => {
    const draft = createDraftTab('c1');
    const key = tabEntryKey(draft);
    const entries = pushAgentTabEntry([], draft);
    const promoted = promoteDraftTab(entries, key, 'thread-99');
    expect(promoted).toEqual([{ kind: 'thread', threadId: 'thread-99' }]);
  });

  it('caps at 5 tabs including drafts', () => {
    let entries = [
      createDraftTab('global'),
      createDraftTab('global'),
      createDraftTab('global'),
      createDraftTab('global'),
      createDraftTab('global'),
    ];
    entries = pushAgentTabEntry(entries, createDraftTab('global'));
    expect(entries).toHaveLength(5);
  });

  it('close draft tab without API side effects', () => {
    const draft = createDraftTab();
    const key = tabEntryKey(draft);
    const entries = pushAgentTabEntry([], draft);
    const { entries: next, activeKey } = closeAgentTabEntry(entries, key, key);
    expect(next).toEqual([]);
    expect(activeKey).toBeNull();
  });

  it('activateAgentTabEntry keeps order when reorder is false', () => {
    const a: ReturnType<typeof createDraftTab> = createDraftTab();
    const b: ReturnType<typeof createDraftTab> = createDraftTab();
    const entries = [a, b];
    expect(activateAgentTabEntry(entries, a, { reorder: false })).toEqual(entries);
  });
});
