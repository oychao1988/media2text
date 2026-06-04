type Props = {
  onRetry?: () => void;
};

export function StreamUnavailable({ onRetry }: Props) {
  return (
    <div className="stream-unavailable" role="alert">
      <p>
        <strong>流不可用</strong>
      </p>
      <p className="hint">直播流加载失败，字幕仍会在右侧更新。</p>
      {onRetry ? (
        <button type="button" className="btn btn-sm" onClick={onRetry}>
          重试
        </button>
      ) : null}
    </div>
  );
}
