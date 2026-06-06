import { useEffect } from 'react';
import { ToastHost } from './components/ToastHost';
import { AppBootstrap } from './features/layout/AppBootstrap';
import { DaemonAppEffects } from './features/daemon/DaemonAppEffects';
import { AppShell } from './features/layout/AppShell';
import { initLayoutStore, useLayoutStore } from './features/layout/useLayoutStore';
import { EventsProvider } from './features/events/EventsProvider';
import { RuntimeProvider } from './features/runtime/RuntimeContext';
import { CreatorsProvider } from './features/creators/CreatorsContext';
import { installDesktopInputGuards } from './lib/desktopInputGuards';
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
    <EventsProvider>
      <RuntimeProvider>
        <DaemonAppEffects />
        <CreatorsProvider forceEmpty={showEmptyCreators}>
          <ToastHost />
          <AppShell />
        </CreatorsProvider>
      </RuntimeProvider>
    </EventsProvider>
  );
}

export function App() {
  useEffect(() => {
    initThemeFromStorage();
    initLayoutStore();
    return installDesktopInputGuards();
  }, []);

  return (
    <AppBootstrap>
      <AppRoot />
    </AppBootstrap>
  );
}
