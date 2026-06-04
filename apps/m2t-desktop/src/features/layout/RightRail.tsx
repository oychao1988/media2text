import { useLayoutStore } from './useLayoutStore';

export function RightRail() {
  const { setRightCollapsed } = useLayoutStore();

  return (
    <div className="right-rail rail" aria-label="右栏折叠快捷栏">
      <button
        type="button"
        className="rail-expand-btn"
        id="expand-right"
        title="展开 Agent 面板"
        aria-label="展开右栏"
        onClick={() => setRightCollapsed(false)}
      >
        ‹
      </button>
    </div>
  );
}
