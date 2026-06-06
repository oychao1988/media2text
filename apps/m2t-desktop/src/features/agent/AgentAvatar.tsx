import { useEffect, useState } from 'react';
import { creatorAvatarUrl } from '../../lib/api';
import { creatorInitial } from '../creators/creatorUtils';
import type { AgentProfile } from './agentProfile';

export type AgentCreatorRef = {
  id: string;
  display_name: string | null;
  avatar_url?: string | null;
  profile_synced_at?: string | null;
};

type AgentAvatarSize = 'tab' | 'option' | 'logo' | 'msg' | 'group';

type AgentAvatarProps = {
  profile: AgentProfile;
  creators: AgentCreatorRef[];
  size?: AgentAvatarSize;
  className?: string;
};

function sizeClass(size: AgentAvatarSize): string {
  switch (size) {
    case 'tab':
      return 'agent-tab-avatar';
    case 'option':
      return 'agent-identity-option-avatar';
    case 'logo':
      return 'agent-identity-logo';
    case 'msg':
      return 'chat-msg-avatar agent';
    case 'group':
      return 'agent-thread-group-avatar';
    default:
      return 'agent-identity-logo';
  }
}

export function AgentAvatar({
  profile,
  creators,
  size = 'logo',
  className,
}: AgentAvatarProps) {
  const creator =
    !profile.isGlobal ? creators.find((c) => c.id === profile.id) : undefined;
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
    if (profile.isGlobal || !creator?.avatar_url) {
      setSrc(null);
      return;
    }
    let cancelled = false;
    void creatorAvatarUrl(creator.id, creator.profile_synced_at).then((url) => {
      if (!cancelled) setSrc(url);
    });
    return () => {
      cancelled = true;
    };
  }, [creator?.avatar_url, creator?.id, creator?.profile_synced_at, profile.isGlobal]);

  const rootClass = [
    sizeClass(size),
    profile.isGlobal ? 'global' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const showImg = Boolean(src && !failed && !profile.isGlobal);

  return (
    <span
      className={rootClass}
      id={size === 'logo' ? 'agent-identity-logo' : undefined}
      aria-hidden="true"
    >
      {showImg ? (
        <img
          className="agent-avatar-img"
          src={src!}
          alt=""
          onError={() => setFailed(true)}
        />
      ) : profile.isGlobal ? (
        profile.abbr
      ) : (
        creatorInitial(creator?.display_name ?? profile.name)
      )}
    </span>
  );
}
