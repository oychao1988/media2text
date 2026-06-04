import { useEffect } from 'react';
import { ToastHost } from './components/ToastHost';
import { AppBootstrap } from './features/layout/AppBootstrap';
import { AppShell } from './features/layout/AppShell';
import { initLayoutStore, useLayoutStore } from './features/layout/useLayoutStore';
import { CreatorsProvider } from './features/creators/CreatorsContext';
import { initThemeFromStorage } from './lib/theme';

function readEmptyListPreview(): boolean {
  try {
    return new URLSearchParams(window.location.search).has('empty-list');
  } catch {
    return false;
  }
}

function AppRoot() {
  const showEmptyCreators = useLayoutStore().showEmptyCreators || readEmptyListPreview();
  return (
    <CreatorsProvider forceEmpty={showEmptyCreators}>
      <ToastHost />
      <AppShell />
    </CreatorsProvider>
  );
}

export function App() {
  useEffect(() => {
    initThemeFromStorage();
    initLayoutStore();
  }, []);

  return (
    <AppBootstrap>
      <AppRoot />
    </AppBootstrap>
  );
}
