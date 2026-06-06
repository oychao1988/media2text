import type { ChatProvider } from './types';

export type AgentModelCatalog = {
  models: string[];
  providerByModel: Map<string, string>;
};

/** Flatten configured LLM providers into model list + owning provider map. */
export function buildAgentModelCatalog(providers: ChatProvider[]): AgentModelCatalog {
  const providerByModel = new Map<string, string>();
  const models: string[] = [];
  for (const p of providers) {
    for (const m of p.models ?? []) {
      if (!m || providerByModel.has(m)) continue;
      providerByModel.set(m, p.name);
      models.push(m);
    }
  }
  return { models, providerByModel };
}
