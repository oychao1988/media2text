import { describe, expect, it } from 'vitest';
import {
  activateAgentTabEntry,
  closeAgentTabEntry,
  createDraftTab,
  openNewDraftForAgent,
  openOrFocusDraftTab,
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

  it('openOrFocusDraftTab reuses existing draft instead of adding another', () => {
    const first = openOrFocusDraftTab([], 'global');
    const second = openOrFocusDraftTab(first.entries, 'c1');
    expect(second.entries).toHaveLength(1);
    expect(second.entries[0]?.kind).toBe('draft');
    if (second.entries[0]?.kind === 'draft') {
      expect(second.entries[0].agentId).toBe('global');
    }
    expect(second.activeKey).toBe(tabEntryKey(first.entries[0]!));
  });

  it('openNewDraftForAgent focuses existing empty draft for same agent', () => {
    const draftB = createDraftTab('creator-b');
    const entries = pushAgentTabEntry([], draftB);
    const result = openNewDraftForAgent(entries, 'creator-b');
    expect(result.entries).toHaveLength(1);
    expect(result.activeKey).toBe(tabEntryKey(draftB));
  });

  it('openNewDraftForAgent creates draft when none exists for agent', () => {
    const globalDraft = createDraftTab('global');
    const entries = pushAgentTabEntry([], globalDraft);
    const result = openNewDraftForAgent(entries, 'creator-a');
    expect(result.entries).toHaveLength(2);
    expect(result.entries[1]?.kind).toBe('draft');
    if (result.entries[1]?.kind === 'draft') {
      expect(result.entries[1].agentId).toBe('creator-a');
    }
    expect(result.activeKey).toBe(tabEntryKey(result.entries[1]!));
  });

  it('openNewDraftForAgent does not reuse draft for different agent', () => {
    const draftA = createDraftTab('creator-a');
    const entries = pushAgentTabEntry([], draftA);
    const result = openNewDraftForAgent(entries, 'creator-b');
    expect(result.entries).toHaveLength(2);
    if (result.entries[1]?.kind === 'draft') {
      expect(result.entries[1].agentId).toBe('creator-b');
    }
  });

  it('openNewDraftForAgent caps at MAX_AGENT_TABS dropping leftmost', () => {
    let entries = [
      createDraftTab('a'),
      createDraftTab('b'),
      createDraftTab('c'),
      createDraftTab('d'),
      createDraftTab('e'),
    ];
    const leftKey = tabEntryKey(entries[0]!);
    const result = openNewDraftForAgent(entries, 'f');
    expect(result.entries).toHaveLength(5);
    expect(result.entries.some((e) => tabEntryKey(e) === leftKey)).toBe(false);
    expect(result.entries[4]?.kind).toBe('draft');
    if (result.entries[4]?.kind === 'draft') {
      expect(result.entries[4].agentId).toBe('f');
    }
  });

  it('openNewDraftForAgent preserves thread tabs when adding draft', () => {
    const thread = { kind: 'thread' as const, threadId: 't1' };
    const entries = pushAgentTabEntry([], thread);
    const result = openNewDraftForAgent(entries, 'creator-b');
    expect(result.entries.some((e) => e.kind === 'thread' && e.threadId === 't1')).toBe(true);
    expect(result.entries.some((e) => e.kind === 'draft' && e.agentId === 'creator-b')).toBe(true);
  });
});
