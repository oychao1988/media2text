export const MAX_AGENT_TABS = 5;

export function pushAgentTab(tabIds: string[], threadId: string): string[] {
  const without = tabIds.filter((id) => id !== threadId);
  const next = [...without, threadId];
  if (next.length <= MAX_AGENT_TABS) return next;
  return next.slice(next.length - MAX_AGENT_TABS);
}

/** Open or focus a tab; skip MRU reorder when clicking an existing top tab. */
export function activateAgentTab(
  tabIds: string[],
  threadId: string,
  opts?: { reorder?: boolean },
): string[] {
  if (!tabIds.includes(threadId)) return pushAgentTab(tabIds, threadId);
  if (opts?.reorder === false) return tabIds;
  return pushAgentTab(tabIds, threadId);
}

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
