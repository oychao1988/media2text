import type { ContextAttachment, ContextMode } from './contextAttachment';
import { AgentAttachmentChip } from './AgentAttachmentChip';

type AgentAttachmentStripProps = {
  attachments: ContextAttachment[];
  contextMode: ContextMode;
  sidebarCreatorId: string | null;
  onRemove: (id: string) => void;
};

export function AgentAttachmentStrip({
  attachments,
  contextMode,
  sidebarCreatorId,
  onRemove,
}: AgentAttachmentStripProps) {
  if (!attachments.length) return null;

  return (
    <div className="agent-attachment-strip" role="list" aria-label="附加文档">
      {attachments.map((attachment) => (
        <AgentAttachmentChip
          key={attachment.id}
          attachment={attachment}
          contextMode={contextMode}
          sidebarCreatorId={sidebarCreatorId}
          onRemove={onRemove}
        />
      ))}
    </div>
  );
}
