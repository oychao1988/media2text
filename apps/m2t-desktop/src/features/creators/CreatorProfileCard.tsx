import type { Creator } from '../../lib/types';
import { CreatorProfileSummary } from './CreatorProfileSummary';

type CreatorProfileCardProps = {
  creator: Creator;
};

export function CreatorProfileCard({ creator }: CreatorProfileCardProps) {
  return (
    <section className="manage-profile-card creator-profile-summary" aria-label="博主资料">
      <CreatorProfileSummary creator={creator} showSyncHint />
    </section>
  );
}
