import type { ToolResultPayload } from '@m2t/shared';

type ToolResultCardProps = {
  result: ToolResultPayload;
};

export function ToolResultCard({ result }: ToolResultCardProps) {
  if (!result.ok && result.error) {
    return (
      <div className="tool-card tool-card--err">
        <strong>工具失败</strong>
        <p>{result.error.message}</p>
        <span className="muted code-cell">{result.error.code}</span>
      </div>
    );
  }

  const preview =
    typeof result.data === 'object' && result.data !== null
      ? JSON.stringify(result.data, null, 2)
      : String(result.data ?? '');

  return (
    <details className="tool-card">
      <summary>工具结果</summary>
      <pre className="tool-card-json">{preview.slice(0, 4000)}</pre>
    </details>
  );
}
