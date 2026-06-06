import { useLayoutStore } from './useLayoutStore';
import type { DesktopLayoutPreset } from './layoutConstants';

const PRESETS: { id: DesktopLayoutPreset; title: string }[] = [
  { id: 'transcript-chat', title: '博主 · 转写 · 对话' },
  { id: 'full', title: '博主 · 播放 · 转写 · 对话' },
  { id: 'chat-only', title: '博主 · 对话' },
];

function PresetIcon({ preset }: { preset: DesktopLayoutPreset }) {
  if (preset === 'transcript-chat') {
    return (
      <span className="layout-preset-icon" aria-hidden="true">
        <span className="lp-col lp-col-sidebar" />
        <span className="lp-col lp-col-transcript" />
        <span className="lp-col lp-col-chat" />
      </span>
    );
  }
  if (preset === 'full') {
    return (
      <span className="layout-preset-icon" aria-hidden="true">
        <span className="lp-col lp-col-sidebar" />
        <span className="lp-col lp-col-center" />
        <span className="lp-col lp-col-stack">
          <span className="lp-stack-top" />
          <span className="lp-stack-bottom" />
        </span>
      </span>
    );
  }
  return (
    <span className="layout-preset-icon" aria-hidden="true">
      <span className="lp-col lp-col-sidebar" />
      <span className="lp-col lp-col-chat" />
    </span>
  );
}

export function DesktopLayoutPresets() {
  const { desktopLayoutPreset, setDesktopLayoutPreset } = useLayoutStore();

  return (
    <div className="layout-preset-group" role="group" aria-label="桌面分区布局">
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
