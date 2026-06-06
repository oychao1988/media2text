import { useLayoutStore } from './useLayoutStore';
import type { DesktopLayoutPreset } from './layoutConstants';

const PRESETS: { id: DesktopLayoutPreset; label: string; title: string }[] = [
  { id: 'full', label: '三栏', title: '博主 + 转写 + 对话' },
  { id: 'transcript-chat', label: '四区', title: '博主 + 转写 | 对话' },
  { id: 'chat-only', label: '对话', title: '博主 + 对话' },
];

function PresetIcon({ preset }: { preset: DesktopLayoutPreset }) {
  if (preset === 'full') {
    return (
      <span className="layout-preset-icon" aria-hidden="true">
        <span className="lp-col lp-col-sidebar" />
        <span className="lp-col lp-col-center" />
        <span className="lp-col-stack">
          <span className="lp-stack-top" />
          <span className="lp-stack-bottom" />
        </span>
      </span>
    );
  }
  if (preset === 'transcript-chat') {
    return (
      <span className="layout-preset-icon" aria-hidden="true">
        <span className="lp-col lp-col-sidebar" />
        <span className="lp-col lp-col-center" />
        <span className="lp-col lp-col-center" />
        <span className="lp-col lp-col-stack lp-col-agent-only" />
      </span>
    );
  }
  return (
    <span className="layout-preset-icon" aria-hidden="true">
      <span className="lp-col lp-col-sidebar" />
      <span className="lp-col lp-col-agent-only" />
    </span>
  );
}

export function DesktopLayoutPresets() {
  const { desktopLayoutPreset, setDesktopLayoutPreset } = useLayoutStore();

  return (
    <div className="layout-preset-group" role="group" aria-label="桌面布局">
      {PRESETS.map((preset) => {
        const active = desktopLayoutPreset === preset.id;
        return (
          <button
            key={preset.id}
            type="button"
            className={`layout-preset-btn${active ? ' active' : ''}`}
            data-layout={preset.id}
            title={preset.title}
            aria-label={preset.title}
            aria-pressed={active}
            onClick={() => setDesktopLayoutPreset(preset.id)}
          >
            <PresetIcon preset={preset.id} />
          </button>
        );
      })}
    </div>
  );
}
