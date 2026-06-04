export type BootstrapPhase = 'loading' | 'error' | 'ready';

export async function pollApiHealth(
  baseUrl: string,
  options?: { fetchFn?: typeof fetch; maxAttempts?: number; intervalMs?: number },
): Promise<void> {
  const fetchFn = options?.fetchFn ?? fetch;
  const maxAttempts = options?.maxAttempts ?? 40;
  const intervalMs = options?.intervalMs ?? 250;
  const healthUrl = `${baseUrl.replace(/\/$/, '')}/api/health`;
  let lastError = '服务未就绪';

  for (let i = 0; i < maxAttempts; i += 1) {
    try {
      const res = await fetchFn(healthUrl, { method: 'GET' });
      if (res.ok) return;
      lastError = `健康检查 HTTP ${res.status}`;
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }

  throw new Error(lastError);
}
