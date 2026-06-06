import { resolveAgentProfile, type AgentProfile } from './agentProfile';
import type { ThreadRow } from './types';

export function threadAgentId(thread: { creator_id: string | null }): string {
  return thread.creator_id ?? 'global';
}

export type AgentThreadGroup = {
  agentId: string;
  profile: AgentProfile;
  threads: ThreadRow[];
};

export function groupThreadsByAgent(
  threads: ThreadRow[],
  creators: Array<{ id: string; display_name: string | null }>,
): AgentThreadGroup[] {
  const byAgent = new Map<string, ThreadRow[]>();
  for (const t of threads) {
    const aid = threadAgentId(t);
    const list = byAgent.get(aid) ?? [];
    list.push(t);
    byAgent.set(aid, list);
  }

  const groups: AgentThreadGroup[] = [];
  const seen = new Set<string>();

  if (byAgent.has('global')) {
    groups.push({
      agentId: 'global',
      profile: resolveAgentProfile(null, creators),
      threads: byAgent.get('global')!,
    });
    seen.add('global');
  }

  for (const c of creators) {
    if (!byAgent.has(c.id) || seen.has(c.id)) continue;
    groups.push({
      agentId: c.id,
      profile: resolveAgentProfile(c.id, creators),
      threads: byAgent.get(c.id)!,
    });
    seen.add(c.id);
  }

  for (const [aid, items] of byAgent) {
    if (seen.has(aid)) continue;
    groups.push({
      agentId: aid,
      profile: resolveAgentProfile(aid === 'global' ? null : aid, creators),
      threads: items,
    });
  }

  return groups;
}

export function filterThreadsByQuery(threads: ThreadRow[], query: string): ThreadRow[] {
  const q = query.trim().toLowerCase();
  if (!q) return threads;
  return threads.filter((t) => (t.title || '').toLowerCase().includes(q));
}
