import { useEffect } from 'react';
import { AppBootstrap } from './features/layout/AppBootstrap';
import { AppShell } from './features/layout/AppShell';
import { initLayoutStore } from './features/layout/useLayoutStore';
import { initThemeFromStorage } from './lib/theme';

export function App() {
  useEffect(() => {
    initThemeFromStorage();
    initLayoutStore();
  }, []);

  return (
    <AppBootstrap>
      <AppShell />
    </AppBootstrap>
  );
}
