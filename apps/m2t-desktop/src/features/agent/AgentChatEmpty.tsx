import { useEffect, useRef, useState } from 'react';
import { AgentAvatar, type AgentCreatorRef } from './AgentAvatar';
import { resolveAgentProfile, AGENT_GLOBAL_PROFILE, type AgentProfile } from './agentProfile';

type Props = {
  agentId: string;
  creators: AgentCreatorRef[];
  onAgentChange: (agentId: string) => void;
};

function buildProfiles(creators: AgentCreatorRef[]): AgentProfile[] {
  return [AGENT_GLOBAL_PROFILE, ...creators.map((c) => resolveAgentProfile(c.id, creators))];
}

export function AgentChatEmpty({ agentId, creators, onAgentChange }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const profiles = buildProfiles(creators);
  const active = resolveAgentProfile(agentId === 'global' ? null : agentId, creators);

  useEffect(() => {
    if (!menuOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('click', onDoc);
    return () => document.removeEventListener('click', onDoc);
  }, [menuOpen]);

  return (
    <div className="agent-chat-empty" id="agent-chat-empty" ref={wrapRef}>
      <div className="agent-identity-bar">
        <AgentAvatar profile={active} creators={creators} size="logo" />
        <div className="agent-identity-picker-wrap">
          <button
            type="button"
            className="agent-identity-picker"
            id="agent-identity-picker"
            aria-haspopup="listbox"
            aria-expanded={menuOpen}
            aria-controls="agent-identity-menu"
            onClick={() => setMenuOpen((v) => !v)}
          >
            <span className="agent-identity-name" id="agent-identity-name">
              {active.name}
            </span>
            <span className="agent-identity-chevron" aria-hidden="true">
              ▾
            </span>
          </button>
        </div>
      </div>
      {!menuOpen ? null : (
        <div
          className="agent-identity-menu-backdrop"
          role="presentation"
          onClick={() => setMenuOpen(false)}
        >
          <div
            className="agent-identity-menu"
            id="agent-identity-menu"
            role="listbox"
            aria-label="选择 Agent"
            onClick={(e) => e.stopPropagation()}
          >
            {profiles.map((p) => {
              const selected = p.id === active.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  className={`agent-identity-option${selected ? ' selected' : ''}`}
                  onClick={() => {
                    onAgentChange(p.id);
                    setMenuOpen(false);
                  }}
                >
                  <AgentAvatar profile={p} creators={creators} size="option" />
                  <span className="agent-identity-option-label">{p.name}</span>
                  {p.isGlobal ? (
                    <span className="agent-identity-option-tag">全局</span>
                  ) : (
                    <span className="agent-identity-option-tag">博主</span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export function composerPlaceholderForAgent(
  agentId: string,
  creators: Array<{ id: string; display_name: string | null }>,
): string {
  if (agentId === 'global') return '输入问题… (@ 引用文件)';
  const profile = resolveAgentProfile(agentId, creators);
  return `向「${profile.name}」Agent 提问…`;
}
