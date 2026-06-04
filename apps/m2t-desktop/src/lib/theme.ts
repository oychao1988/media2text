const THEME_KEY = 'm2t-desktop-theme';

export type ThemeMode = 'light' | 'dark';

export function readStoredTheme(): ThemeMode {
  try {
    const t = localStorage.getItem(THEME_KEY);
    return t === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

export function applyTheme(theme: ThemeMode): void {
  document.documentElement.setAttribute('data-theme', theme);
}

export function writeStoredTheme(theme: ThemeMode): void {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* ignore quota */
  }
  applyTheme(theme);
}

export function initThemeFromStorage(): ThemeMode {
  const theme = readStoredTheme();
  applyTheme(theme);
  return theme;
}
