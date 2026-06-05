import { useEffect, useState } from 'react';
import { creatorAvatarUrl } from '../../lib/api';
import type { StatusLight } from '../../lib/types';
import { creatorInitial } from './creatorUtils';
import { StatusLight as StatusLightBadge } from './StatusLight';

type CreatorAvatarProps = {
  creatorId: string;
  displayName: string | null;
  avatarUrl?: string | null;
  profileSyncedAt?: string | null;
  /** manage: 监控管理列表/抽屉；list: 左侧博主列表与折叠栏 */
  variant?: 'manage' | 'list';
  size?: 'sm' | 'lg';
  light?: StatusLight;
  abbr?: string;
  className?: string;
};

export function CreatorAvatar({
  creatorId,
  displayName,
  avatarUrl,
  profileSyncedAt,
  variant = 'manage',
  size = 'sm',
  light,
  abbr,
  className,
}: CreatorAvatarProps) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
    if (!avatarUrl) {
      setSrc(null);
      return;
    }
    let cancelled = false;
    void creatorAvatarUrl(creatorId, profileSyncedAt).then((url) => {
      if (!cancelled) setSrc(url);
    });
    return () => {
      cancelled = true;
    };
  }, [creatorId, avatarUrl, profileSyncedAt]);

  const baseClass = variant === 'list' ? 'avatar' : 'manage-avatar';
  const rootClass = [baseClass, variant === 'manage' && size === 'lg' ? 'lg' : '', className]
    .filter(Boolean)
    .join(' ');
  const showImg = Boolean(src && !failed);

  return (
    <div className={rootClass} aria-hidden="true">
      {showImg ? (
        <img className="creator-avatar-img" src={src!} alt="" onError={() => setFailed(true)} />
      ) : (
        creatorInitial(displayName)
      )}
      {light ? <StatusLightBadge light={light} abbr={abbr} /> : null}
    </div>
  );
}
