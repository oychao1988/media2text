export type AgentProfile = {
  id: string;
  name: string;
  abbr: string;
  isGlobal: boolean;
};

export const AGENT_GLOBAL_PROFILE: AgentProfile = {
  id: 'global',
  name: '灵犀',
  abbr: '灵',
  isGlobal: true,
};

export function agentAbbr(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return '?';
  return trimmed.length <= 2 ? trimmed : trimmed.slice(0, 2);
}

export function resolveAgentProfile(
  threadCreatorId: string | null | undefined,
  creators: Array<{ id: string; display_name: string | null }>,
): AgentProfile {
  if (!threadCreatorId) return AGENT_GLOBAL_PROFILE;
  const creator = creators.find((c) => c.id === threadCreatorId);
  const name = creator?.display_name ?? threadCreatorId;
  return {
    id: threadCreatorId,
    name,
    abbr: agentAbbr(name),
    isGlobal: false,
  };
}
