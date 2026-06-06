import { useEffect, useRef, useState } from 'react';
import { resolveAgentProfile, AGENT_GLOBAL_PROFILE, type AgentProfile } from './agentProfile';

type Props = {
  agentId: string;
  creators: Array<{ id: string; display_name: string | null }>;
  onAgentChange: (agentId: string) => void;
};

function buildProfiles(creators: Array<{ id: string; display_name: string | null }>): AgentProfile[] {
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
    <div className="agent-chat-empty" id="agent-chat-empty">
      <div className="agent-identity-bar">
        <div
          className={`agent-identity-logo${active.isGlobal ? ' global' : ''}`}
          id="agent-identity-logo"
          aria-hidden="true"
        >
          {active.abbr}
        </div>
        <div className="agent-identity-picker-wrap" ref={wrapRef}>
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
          {!menuOpen ? null : (
            <div className="agent-identity-menu" id="agent-identity-menu" role="listbox">
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
                    <span
                      className={`agent-identity-option-avatar${p.isGlobal ? ' global' : ''}`}
                      aria-hidden="true"
                    >
                      {p.abbr}
                    </span>
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
          )}
        </div>
      </div>
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
