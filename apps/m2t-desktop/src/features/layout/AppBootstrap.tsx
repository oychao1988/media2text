import { type ReactNode, useCallback, useEffect, useState } from 'react';
import { browserDevHint, resolveApiBaseUrl, runningInTauri } from '../../lib/tauriBridge';
import { pollApiHealth, type BootstrapPhase } from './bootstrapHealth';

type Props = {
  children: ReactNode;
};

export function AppBootstrap({ children }: Props) {
  const [phase, setPhase] = useState<BootstrapPhase>('loading');
  const [errorMessage, setErrorMessage] = useState('');

  const runBootstrap = useCallback(async () => {
    setPhase('loading');
    setErrorMessage('');
    try {
      const baseUrl = await resolveApiBaseUrl();
      await pollApiHealth(
        baseUrl,
        import.meta.env.MODE === 'test' ? { maxAttempts: 3, intervalMs: 0 } : undefined,
      );
      setPhase('ready');
    } catch (err) {
      setPhase('error');
      setErrorMessage(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void runBootstrap();
  }, [runBootstrap]);

  if (phase === 'loading') {
    return (
      <div className="app-bootstrap" role="status" aria-live="polite">
        <div className="app-bootstrap-card">
          <div className="app-bootstrap-spinner" aria-hidden="true" />
          <p className="app-bootstrap-title">正在启动服务…</p>
          <p className="app-bootstrap-hint">正在连接本地 Python API</p>
        </div>
      </div>
    );
  }

  if (phase === 'error') {
    return (
      <div className="app-bootstrap app-bootstrap--error" role="alert">
        <div className="app-bootstrap-card">
          <p className="app-bootstrap-title">服务启动失败</p>
          {!runningInTauri() ? (
            <p className="app-bootstrap-hint app-bootstrap-hint--warn">{browserDevHint()}</p>
          ) : null}
          <p className="app-bootstrap-hint">{errorMessage || '未知错误'}</p>
          <button type="button" className="btn btn-primary" onClick={() => void runBootstrap()}>
            重试
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
