import { invoke, isTauri } from '@tauri-apps/api/core';

const BROWSER_DEV_API_BASE =
  (import.meta.env.VITE_M2T_API_BASE_URL as string | undefined)?.trim() ||
  'http://127.0.0.1:8765';

export function runningInTauri(): boolean {
  return isTauri();
}

/** Resolve FastAPI base URL: Tauri sidecar in app window, fixed localhost in browser dev. */
export async function resolveApiBaseUrl(): Promise<string> {
  if (!isTauri()) {
    return BROWSER_DEV_API_BASE.replace(/\/$/, '');
  }
  const url = (await invoke<string>('get_api_base_url')).trim();
  if (!url) {
    throw new Error('未获取到 API 地址');
  }
  return url.replace(/\/$/, '');
}

export async function tauriInvoke<T>(
  cmd: string,
  args?: Record<string, unknown>,
): Promise<T> {
  if (!isTauri()) {
    throw new Error(
      'Agent 与 Sidecar 控制需在 Tauri 桌面窗口中使用。请运行 `pnpm --filter m2t-desktop tauri dev` 并使用弹出的应用窗口，勿在浏览器标签打开 localhost:1420。',
    );
  }
  return invoke<T>(cmd, args);
}

export function browserDevHint(): string {
  return (
    '当前在浏览器中打开，无法注入 Tauri API。请使用 `pnpm --filter m2t-desktop tauri dev` 弹出的桌面窗口；' +
    '若仅调试 UI，可先 `media2text serve --port 8765`，本页将连接 ' +
    BROWSER_DEV_API_BASE +
    '（可通过 VITE_M2T_API_BASE_URL 覆盖）。'
  );
}
