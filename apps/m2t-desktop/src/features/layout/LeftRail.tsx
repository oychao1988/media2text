import { MOCK_CREATORS } from '../creators/mockCreators';
import { useLayoutStore } from './useLayoutStore';

type Props = {
  selectedCreatorId: string;
  onSelectCreator: (id: string) => void;
};

export function LeftRail({ selectedCreatorId, onSelectCreator }: Props) {
  const { expandLeftPanel, setUserMenuOpen, userMenuOpen } = useLayoutStore();

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
        {MOCK_CREATORS.map((creator) => {
          const live = creator.light === 'red' || creator.light === 'green';
          return (
            <div
              key={creator.id}
              className={`rail-dot${selectedCreatorId === creator.id ? ' selected' : ''}${live ? ' is-live' : ''}`}
              role="listitem"
              tabIndex={0}
              data-creator={creator.id}
              title={`${creator.name} · ${creator.sub}`}
              onClick={() => onSelectCreator(creator.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onSelectCreator(creator.id);
                }
              }}
            >
              <span>{creator.initial}</span>
              <span className={`light ${creator.light}`} aria-hidden="true" />
            </div>
          );
        })}
      </div>
      <div className="rail-section-bottom">
        <button
          type="button"
          className="rail-daemon"
          id="rail-daemon"
          title="Daemon 运行中 · 点击展开侧栏"
          aria-label="Daemon 状态"
          onClick={expandLeftPanel}
        >
          <span className="rail-daemon-dot live" id="rail-daemon-dot" aria-hidden="true" />
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
