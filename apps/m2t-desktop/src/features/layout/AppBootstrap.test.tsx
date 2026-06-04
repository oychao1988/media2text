import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppBootstrap } from './AppBootstrap';

const invokeMock = vi.fn();
const fetchMock = vi.fn();

vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => invokeMock(...args),
}));

describe('AppBootstrap', () => {
  beforeEach(() => {
    invokeMock.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  it('shows loading then ready when health succeeds', async () => {
    invokeMock.mockResolvedValue('http://127.0.0.1:8765');
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
    expect(invokeMock).toHaveBeenCalledWith('get_api_base_url');
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8765/api/health',
      expect.objectContaining({ method: 'GET' }),
    );
  });

  it('shows error and retries after health failure', async () => {
    invokeMock.mockResolvedValue('http://127.0.0.1:8765');
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

  it('shows error when invoke returns empty base url', async () => {
    invokeMock.mockResolvedValue('');

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
