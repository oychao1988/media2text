import type { Creator } from '../../lib/types';
import { CreatorAvatar } from './CreatorAvatar';
import { CreatorHoverPopover } from './CreatorHoverPopover';
import { formatCreatorSub, isCreatorLive } from './creatorUtils';

type Props = {
  creators: Creator[];
  selectedId: string | null;
  loading?: boolean;
  error?: string | null;
  onSelect: (creator: Creator) => void;
  onRetry?: () => void;
};

export function CreatorList({
  creators,
  selectedId,
  loading,
  error,
  onSelect,
  onRetry,
}: Props) {
  if (loading) return null;
  if (error) {
    return (
      <div className="creator-list-error" role="alert">
        <p>{error}</p>
        {onRetry ? (
          <button type="button" className="btn btn-sm" onClick={onRetry}>
            重试
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <nav className="creator-list" id="creator-list" aria-label="已监控博主">
      {creators.map((creator) => {
        const selected = creator.id === selectedId;
        const live = isCreatorLive(creator);
        return (
          <CreatorHoverPopover key={creator.id} creator={creator}>
            <div
              className={`creator-item${selected ? ' selected' : ''}${creator.profile_stale ? ' stale' : ''}`}
              tabIndex={0}
              role="button"
              aria-current={selected ? 'true' : undefined}
              data-creator={creator.id}
              onClick={() => onSelect(creator)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onSelect(creator);
                }
              }}
            >
              <div className={`avatar-wrap${live ? ' is-live' : ''}`}>
                <CreatorAvatar
                  variant="list"
                  creatorId={creator.id}
                  displayName={creator.display_name}
                  avatarUrl={creator.avatar_url}
                  profileSyncedAt={creator.profile_synced_at}
                  light={creator.status_light}
                  abbr={creator.status_abbr}
                  statusLabel={creator.status_label}
                />
              </div>
              <div className="creator-info">
                <div className="creator-name">{creator.display_name ?? creator.unique_id ?? creator.id}</div>
                <div className="creator-sub">{formatCreatorSub(creator)}</div>
              </div>
            </div>
          </CreatorHoverPopover>
        );
      })}
    </nav>
  );
}
