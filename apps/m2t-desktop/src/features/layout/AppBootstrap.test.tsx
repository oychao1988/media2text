import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppBootstrap } from './AppBootstrap';

const resolveApiBaseUrlMock = vi.fn();
const runningInTauriMock = vi.fn(() => true);
const fetchMock = vi.fn();

vi.mock('../../lib/tauriBridge', () => ({
  resolveApiBaseUrl: (...args: unknown[]) => resolveApiBaseUrlMock(...args),
  runningInTauri: () => runningInTauriMock(),
  browserDevHint: () => 'browser-hint',
}));

describe('AppBootstrap', () => {
  beforeEach(() => {
    resolveApiBaseUrlMock.mockReset();
    runningInTauriMock.mockReturnValue(true);
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  it('shows loading then ready when health succeeds', async () => {
    resolveApiBaseUrlMock.mockResolvedValue('http://127.0.0.1:8765');
    fetchMock.mockResolvedValue({ ok: true, status: 200 });

    render(
      <AppBootstrap>
        <div data-testid="shell">ready-shell</div>
      </AppBootstrap>,
    );

    expect(screen.getByText('正在启动服务…')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('shell')).toBeInTheDocument();
    });
    expect(resolveApiBaseUrlMock).toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8765/api/health',
      expect.objectContaining({ method: 'GET' }),
    );
  });

  it('shows error and retries after health failure', async () => {
    resolveApiBaseUrlMock.mockResolvedValue('http://127.0.0.1:8765');
    fetchMock.mockResolvedValue({ ok: false, status: 503 });

    render(
      <AppBootstrap>
        <div data-testid="shell">ready-shell</div>
      </AppBootstrap>,
    );

    await waitFor(() => {
      expect(screen.getByText('服务启动失败')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('shell')).not.toBeInTheDocument();

    fetchMock.mockResolvedValue({ ok: true, status: 200 });
    await userEvent.click(screen.getByRole('button', { name: '重试' }));

    await waitFor(() => {
      expect(screen.getByTestId('shell')).toBeInTheDocument();
    });
  });

  it('shows error when api base url is empty', async () => {
    resolveApiBaseUrlMock.mockRejectedValue(new Error('未获取到 API 地址'));

    render(
      <AppBootstrap>
        <div data-testid="shell">ready-shell</div>
      </AppBootstrap>,
    );

    await waitFor(() => {
      expect(screen.getByText('服务启动失败')).toBeInTheDocument();
      expect(screen.getByText('未获取到 API 地址')).toBeInTheDocument();
    });
  });
});
