export const MAX_AGENT_TABS = 5;

export function pushAgentTab(tabIds: string[], threadId: string): string[] {
  const without = tabIds.filter((id) => id !== threadId);
  const next = [...without, threadId];
  if (next.length <= MAX_AGENT_TABS) return next;
  return next.slice(next.length - MAX_AGENT_TABS);
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
