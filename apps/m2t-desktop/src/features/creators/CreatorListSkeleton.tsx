export function CreatorListSkeleton() {
  return (
    <div className="creator-list-skeleton" aria-busy="true" aria-label="加载博主列表">
      {[0, 1, 2].map((i) => (
        <div key={i} className="creator-skeleton-row">
          <div className="creator-skeleton-avatar" />
          <div className="creator-skeleton-lines">
            <div className="creator-skeleton-line creator-skeleton-line--wide" />
            <div className="creator-skeleton-line" />
          </div>
        </div>
      ))}
    </div>
  );
}
