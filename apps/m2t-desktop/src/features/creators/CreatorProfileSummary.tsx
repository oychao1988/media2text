import type { Creator } from '../../lib/types';
import { CreatorAvatar } from './CreatorAvatar';
import {
  formatCreatorSub,
  formatFollowerCount,
  formatProfileSyncedAt,
  hasSyncedProfile,
} from './creatorUtils';

type CreatorProfileSummaryProps = {
  creator: Creator;
  /** 未同步资料时在管理页显示提示；浮窗默认不显示 */
  showSyncHint?: boolean;
  /** 浮窗等紧凑场景显示直播状态行 */
  showStatus?: boolean;
  avatarSize?: 'sm' | 'lg';
};

export function CreatorProfileSummary({
  creator,
  showSyncHint = false,
  showStatus = false,
  avatarSize = 'lg',
}: CreatorProfileSummaryProps) {
  const name = creator.display_name ?? creator.unique_id ?? creator.id;
  const handle = creator.unique_id ? `@${creator.unique_id}` : null;
  const followers = formatFollowerCount(creator.follower_count);
  const synced = formatProfileSyncedAt(creator.profile_synced_at);
  const syncedProfile = hasSyncedProfile(creator);

  return (
    <>
      <CreatorAvatar
        creatorId={creator.id}
        displayName={creator.display_name}
        avatarUrl={creator.avatar_url}
        profileSyncedAt={creator.profile_synced_at}
        size={avatarSize}
      />
      <div className="creator-profile-body">
        <h4 className="creator-profile-name">{name}</h4>
        <p className="creator-profile-meta">
          {handle ? <span>{handle}</span> : null}
          {handle ? <span aria-hidden="true"> · </span> : null}
          <span className="platform-tag">{creator.platform}</span>
        </p>
        {showStatus ? (
          <p className={`creator-profile-status status-${creator.status_light}`}>
            {formatCreatorSub(creator)}
          </p>
        ) : null}
        {creator.live_snapshot?.title ? (
          <p className="creator-profile-live-title">{creator.live_snapshot.title}</p>
        ) : null}
        {creator.signature ? <p className="creator-profile-signature">{creator.signature}</p> : null}
        {syncedProfile ? (
          <p className="creator-profile-stats">
            {followers ? <span>粉丝 {followers}</span> : null}
            {followers && synced ? <span aria-hidden="true"> · </span> : null}
            {synced ? <span>同步于 {synced}</span> : null}
          </p>
        ) : showSyncHint ? (
          <p className="hint creator-profile-hint">点击「同步资料」获取头像与简介</p>
        ) : null}
      </div>
    </>
  );
}
