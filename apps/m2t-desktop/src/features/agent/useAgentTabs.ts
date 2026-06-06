export const MAX_AGENT_TABS = 5;

export type AgentTabEntry =
  | { kind: 'draft'; draftId: string; agentId: string }
  | { kind: 'thread'; threadId: string };

export function tabEntryKey(entry: AgentTabEntry): string {
  return entry.kind === 'draft' ? `draft:${entry.draftId}` : `thread:${entry.threadId}`;
}

export function createDraftTab(agentId = 'global'): AgentTabEntry {
  return {
    kind: 'draft',
    draftId: `draft-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    agentId,
  };
}

export function findDraftTab(entries: AgentTabEntry[]): AgentTabEntry | undefined {
  return entries.find((e) => e.kind === 'draft');
}

/** Reuse the lone empty draft tab instead of opening duplicates. */
export function openOrFocusDraftTab(
  entries: AgentTabEntry[],
  agentId = 'global',
): { entries: AgentTabEntry[]; activeKey: string } {
  const existing = findDraftTab(entries);
  if (existing) {
    const key = tabEntryKey(existing);
    return {
      entries: pushAgentTabEntry(entries, existing),
      activeKey: key,
    };
  }
  const entry = createDraftTab(agentId);
  return { entries: pushAgentTabEntry(entries, entry), activeKey: tabEntryKey(entry) };
}

export function pushAgentTabEntry(entries: AgentTabEntry[], entry: AgentTabEntry): AgentTabEntry[] {
  const key = tabEntryKey(entry);
  const without = entries.filter((e) => tabEntryKey(e) !== key);
  const next = [...without, entry];
  if (next.length <= MAX_AGENT_TABS) return next;
  return next.slice(next.length - MAX_AGENT_TABS);
}

/** Open or focus a tab; skip MRU reorder when clicking an existing top tab. */
export function activateAgentTabEntry(
  entries: AgentTabEntry[],
  entry: AgentTabEntry,
  opts?: { reorder?: boolean },
): AgentTabEntry[] {
  const key = tabEntryKey(entry);
  if (!entries.some((e) => tabEntryKey(e) === key)) return pushAgentTabEntry(entries, entry);
  if (opts?.reorder === false) return entries;
  return pushAgentTabEntry(entries, entry);
}

export function closeAgentTabEntry(
  entries: AgentTabEntry[],
  key: string,
  activeKey: string | null,
): { entries: AgentTabEntry[]; activeKey: string | null } {
  const idx = entries.findIndex((e) => tabEntryKey(e) === key);
  if (idx < 0) return { entries, activeKey };
  const nextEntries = entries.filter((e) => tabEntryKey(e) !== key);
  if (activeKey !== key) {
    return { entries: nextEntries, activeKey };
  }
  const fallback = nextEntries[idx] ?? nextEntries[idx - 1] ?? nextEntries[0];
  const nextActive = fallback ? tabEntryKey(fallback) : null;
  return { entries: nextEntries, activeKey: nextActive };
}

export function promoteDraftTab(
  entries: AgentTabEntry[],
  draftKey: string,
  threadId: string,
): AgentTabEntry[] {
  return entries.map((e) =>
    tabEntryKey(e) === draftKey ? { kind: 'thread' as const, threadId } : e,
  );
}

export function removeThreadFromTabs(entries: AgentTabEntry[], threadId: string): AgentTabEntry[] {
  return entries.filter((e) => !(e.kind === 'thread' && e.threadId === threadId));
}

/** @deprecated use pushAgentTabEntry with thread entry */
export function pushAgentTab(tabIds: string[], threadId: string): string[] {
  const without = tabIds.filter((id) => id !== threadId);
  const next = [...without, threadId];
  if (next.length <= MAX_AGENT_TABS) return next;
  return next.slice(next.length - MAX_AGENT_TABS);
}

/** @deprecated */
export function activateAgentTab(
  tabIds: string[],
  threadId: string,
  opts?: { reorder?: boolean },
): string[] {
  if (!tabIds.includes(threadId)) return pushAgentTab(tabIds, threadId);
  if (opts?.reorder === false) return tabIds;
  return pushAgentTab(tabIds, threadId);
}

/** @deprecated */
export function closeAgentTab(
  tabIds: string[],
  threadId: string,
  activeId: string | null,
): { tabIds: string[]; activeId: string | null } {
  const idx = tabIds.indexOf(threadId);
  if (idx < 0) return { tabIds, activeId };
  const nextTabs = tabIds.filter((id) => id !== threadId);
  if (activeId !== threadId) {
    return { tabIds: nextTabs, activeId };
  }
  const nextActive = nextTabs[idx] ?? nextTabs[idx - 1] ?? null;
  return { tabIds: nextTabs, activeId: nextActive };
}
