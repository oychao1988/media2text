import type { ContextAttachment, ContextMode } from './contextAttachment';
import { filterByContextMode } from './agentAttachments';

function formatSize(bytes?: number): string | null {
  if (bytes == null || bytes <= 0) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function docTypeLabel(docType: ContextAttachment['docType']): string {
  return docType === 'transcript' ? '转写' : '摘要';
}

type AgentAttachmentChipProps = {
  attachment: ContextAttachment;
  contextMode: ContextMode;
  sidebarCreatorId: string | null;
  onRemove: (id: string) => void;
};

export function AgentAttachmentChip({
  attachment,
  contextMode,
  sidebarCreatorId,
  onRemove,
}: AgentAttachmentChipProps) {
  const enabled =
    contextMode === 'both' ||
    filterByContextMode([attachment], contextMode).length > 0;
  const showCreatorPrefix =
    Boolean(attachment.creatorName) &&
    attachment.creatorId !== sidebarCreatorId;
  const label = showCreatorPrefix
    ? `${attachment.creatorName} · ${attachment.label}`
    : attachment.label;
  const size = formatSize(attachment.sizeBytes);
  const removeLabel = `移除 ${label} ${docTypeLabel(attachment.docType)}`;

  return (
    <div
      className={`agent-attachment-chip${enabled ? '' : ' agent-attachment-chip--muted'}`}
      title={enabled ? undefined : '当前 Tab 未注入上下文'}
    >
      <span className="agent-attachment-icon" aria-hidden="true">
        📄
      </span>
      <div className="agent-attachment-meta">
        <span className="agent-attachment-label">{label}</span>
        <span className="agent-attachment-type">
          {docTypeLabel(attachment.docType)}
          {size ? ` · ${size}` : ''}
        </span>
      </div>
      <button
        type="button"
        className="agent-attachment-remove"
        aria-label={removeLabel}
        onClick={() => onRemove(attachment.id)}
      >
        ×
      </button>
    </div>
  );
}
