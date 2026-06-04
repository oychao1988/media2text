import type { Creator } from '../../lib/types';
import { useDaemonRunning } from '../daemon/DaemonCard';
import { creatorInitial } from '../creators/creatorUtils';
import { StatusLight } from '../creators/StatusLight';
import { useLayoutStore } from './useLayoutStore';

type Props = {
  creators: Creator[];
  selectedCreatorId: string | null;
  onSelectCreator: (id: string) => void;
};

export function LeftRail({ creators, selectedCreatorId, onSelectCreator }: Props) {
  const { expandLeftPanel, setUserMenuOpen, userMenuOpen } = useLayoutStore();
  const daemonRunning = useDaemonRunning();

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
          const live = creator.is_live || creator.status_light === 'green';
          return (
            <div
              key={creator.id}
              className={`rail-dot${selectedCreatorId === creator.id ? ' selected' : ''}${live ? ' is-live' : ''}`}
              role="listitem"
              tabIndex={0}
              data-creator={creator.id}
              title={creator.display_name ?? creator.id}
              onClick={() => onSelectCreator(creator.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onSelectCreator(creator.id);
                }
              }}
            >
              <span>{creatorInitial(creator.display_name)}</span>
              <StatusLight light={creator.status_light} className="rail-light" />
            </div>
          );
        })}
      </div>
      <div className="rail-section-bottom">
        <button
          type="button"
          className="rail-daemon"
          id="rail-daemon"
          title="Daemon · 点击展开侧栏"
          aria-label="Daemon 状态"
          onClick={expandLeftPanel}
        >
          <span
            className={`rail-daemon-dot${daemonRunning ? ' live' : ''}`}
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
          O
        </button>
      </div>
    </div>
  );
}
