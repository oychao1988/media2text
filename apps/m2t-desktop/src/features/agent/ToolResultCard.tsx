import type { ToolResultPayload } from '@m2t/shared';

type ToolResultCardProps = {
  result: ToolResultPayload;
  toolName?: string;
};

export function ToolResultCard({ result, toolName = 'tool' }: ToolResultCardProps) {
  const headerLabel = result.ok ? toolName : `${toolName} · error`;

  if (!result.ok && result.error) {
    return (
      <div className="tool-card tool-card--err">
        <div className="tool-card-header">
          <span>{headerLabel}</span>
        </div>
        <div className="tool-card-body">
          <p>{result.error.message}</p>
          <span className="muted code-cell">{result.error.code}</span>
        </div>
      </div>
    );
  }

  const preview =
    typeof result.data === 'object' && result.data !== null
      ? JSON.stringify(result.data, null, 2)
      : String(result.data ?? '');

  return (
    <div className="tool-card">
      <div className="tool-card-header">
        <span>{headerLabel}</span>
      </div>
      <div className="tool-card-body">
        <pre className="tool-card-json">{preview.slice(0, 4000)}</pre>
      </div>
    </div>
  );
}
