import { MOCK_CREATORS, type MockCreator } from './mockCreators';

type Props = {
  selectedId: string;
  onSelect: (creator: MockCreator) => void;
};

export function CreatorList({ selectedId, onSelect }: Props) {
  return (
    <nav className="creator-list" id="creator-list" aria-label="已监控博主">
      {MOCK_CREATORS.map((creator) => {
        const selected = creator.id === selectedId;
        const live = creator.light === 'red' || creator.light === 'green';
        return (
          <div
            key={creator.id}
            className={`creator-item${selected ? ' selected' : ''}`}
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
              <div className="avatar">{creator.initial}</div>
              <span
                className={`light ${creator.light}`}
                data-abbr={creator.abbr}
                title={creator.ariaLabel}
                aria-label={creator.ariaLabel}
                role="img"
              />
            </div>
            <div className="creator-info">
              <div className="creator-name">{creator.name}</div>
              <div className="creator-sub">{creator.sub}</div>
            </div>
          </div>
        );
      })}
    </nav>
  );
}
