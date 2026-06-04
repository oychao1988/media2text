import { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';

export function App() {
  const [apiBaseUrl, setApiBaseUrl] = useState<string>('');

  useEffect(() => {
    invoke<string>('get_api_base_url')
      .then(setApiBaseUrl)
      .catch(() => setApiBaseUrl(''));
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-950 text-zinc-100">
      <div className="space-y-2 text-center">
        <h1 className="text-xl font-semibold">media2text desktop</h1>
        <p className="text-sm text-zinc-400">
          API: {apiBaseUrl || 'starting…'}
        </p>
      </div>
    </main>
  );
}
