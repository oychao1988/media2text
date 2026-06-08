import type { Creator } from '../../lib/types';
import { healthAriaLabel } from '../daemon/daemonHealth';
import { useRuntime } from '../runtime/RuntimeContext';
import { CreatorAvatar } from '../creators/CreatorAvatar';
import { CreatorHoverPopover } from '../creators/CreatorHoverPopover';
import { isCreatorLive } from '../creators/creatorUtils';
import { useLayoutStore } from './useLayoutStore';
import { userDisplayInitial } from './userDisplay';

type Props = {
  creators: Creator[];
  selectedCreatorId: string | null;
  onSelectCreator: (id: string) => void;
};

export function LeftRail({ creators, selectedCreatorId, onSelectCreator }: Props) {
  const { expandLeftPanel, setUserMenuOpen, setDaemonMenuOpen, userMenuOpen, daemonMenuOpen } =
    useLayoutStore();
  const { runtime } = useRuntime();

  const health = runtime?.health ?? 'stopped';
  const running = runtime?.daemon.running ?? false;
  const statusLabel = healthAriaLabel(health, running);

  return (
    <div className="left-rail rail" aria-label="折叠快捷栏">
      <div className="rail-section-top">
        <button
          type="button"
          className="rail-expand-btn"
          id="expand-left"
          title="展开监控列表"
          aria-label="展开左栏"
          onClick={expandLeftPanel}
        >
          ›
        </button>
      </div>
      <div className="rail-scroll" role="list" aria-label="博主快捷选择">
        {creators.map((creator) => {
          const live = isCreatorLive(creator);
          return (
            <CreatorHoverPopover key={creator.id} creator={creator}>
              <div
                className={`rail-dot${selectedCreatorId === creator.id ? ' selected' : ''}${live ? ' is-live' : ''}`}
                role="listitem"
                tabIndex={0}
                data-creator={creator.id}
                onClick={() => onSelectCreator(creator.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelectCreator(creator.id);
                  }
                }}
              >
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
            </CreatorHoverPopover>
          );
        })}
      </div>
      <div className="rail-section-bottom">
        <button
          type="button"
          className="rail-daemon"
          id="rail-daemon"
          title={`${statusLabel} · 点击查看`}
          aria-label={statusLabel}
          aria-haspopup="dialog"
          aria-expanded={daemonMenuOpen}
          aria-controls="daemon-monitor-menu"
          onClick={() => setDaemonMenuOpen(!daemonMenuOpen)}
        >
          <span
            className={`rail-daemon-dot health-${health}${running ? ' live' : ''}`}
            id="rail-daemon-dot"
            aria-hidden="true"
          />
        </button>
        <button
          type="button"
          className="rail-user-btn"
          id="rail-user-menu"
          title="用户菜单 · 系统配置 / 监控管理"
          aria-label="用户菜单"
          aria-haspopup="menu"
          aria-expanded={userMenuOpen}
          aria-controls="user-menu"
          onClick={(e) => {
            e.stopPropagation();
            setUserMenuOpen(!userMenuOpen);
          }}
        >
          {userDisplayInitial()}
        </button>
      </div>
    </div>
  );
}
