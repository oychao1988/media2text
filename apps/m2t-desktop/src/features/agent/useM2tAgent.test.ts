import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useM2tAgent } from './useM2tAgent';
import * as api from '../../lib/api';
import * as toast from '../../lib/toast';

type MockWs = {
  url: string;
  onopen: (() => void) | null;
  onmessage: ((ev: MessageEvent) => void) | null;
  onclose: (() => void) | null;
  onerror: (() => void) | null;
  close: ReturnType<typeof vi.fn>;
};

const mockSockets: MockWs[] = [];

class MockWebSocket {
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    const sock: MockWs = this;
    mockSockets.push(sock);
    queueMicrotask(() => sock.onopen?.());
  }
}

vi.mock('../../lib/api', async (importOriginal) => {
  const orig = await importOriginal<typeof api>();
  return {
    ...orig,
    apiGet: vi.fn(),
    apiPost: vi.fn(),
    apiPatch: vi.fn(),
    buildWsUrl: vi.fn(async (path: string) => `ws://127.0.0.1:8765${path}`),
  };
});

vi.mock('../../lib/toast', () => ({
  showToast: vi.fn(),
}));

const apiGet = vi.mocked(api.apiGet);
const apiPost = vi.mocked(api.apiPost);
const apiPatch = vi.mocked(api.apiPatch);

function emitWs(event: object) {
  const sock = mockSockets[mockSockets.length - 1];
  sock?.onmessage?.({ data: JSON.stringify(event) } as MessageEvent);
}

describe('useM2tAgent (M2 WS + turn)', () => {
  beforeEach(() => {
    mockSockets.length = 0;
    vi.stubGlobal('WebSocket', MockWebSocket);
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/api/chat/providers') {
        return { providers: [{ name: 'nvidia', models: ['test'], configured: true }] };
      }
      if (path === '/api/agent/threads') {
        return { threads: [{ id: 'thread-1', model: 'auto' }] };
      }
      if (path === '/api/agent/threads/thread-1/messages') {
        return {
          messages: [
            { id: 'u1', role: 'user', content: 'hello' },
            { id: 'a1', role: 'assistant', content: 'reconciled' },
          ],
        };
      }
      throw new Error(`unexpected GET ${path}`);
    });
    apiPost.mockResolvedValue({ turnId: 'turn-1' });
    apiPatch.mockResolvedValue({});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('connects WS /api/agent/stream for threadId', async () => {
    renderHook(() =>
      useM2tAgent({
        threadId: 'thread-1',
        creatorId: 'creator-1',
        sessionContext: { sessionId: null, contextMode: 'both' },
      }),
    );
    await waitFor(() => {
      expect(mockSockets.length).toBeGreaterThan(0);
      expect(mockSockets[0].url).toContain('/api/agent/stream?threadId=thread-1');
    });
  });

  it('becomes ready on sidecar.ready and reconciles on turn.end', async () => {
    const { result } = renderHook(() =>
      useM2tAgent({
        threadId: 'thread-1',
        creatorId: 'creator-1',
        sessionContext: { sessionId: null, contextMode: 'both' },
      }),
    );

    await waitFor(() => expect(mockSockets.length).toBe(1));
    act(() => {
      emitWs({ type: 'sidecar.ready', payload: { version: 'test' } });
    });
    await waitFor(() => expect(result.current.status).toBe('ready'));

    act(() => {
      emitWs({ type: 'turn.end', payload: { durationMs: 100 } });
    });
    await waitFor(() =>
      expect(result.current.messages.some((m) => m.role === 'assistant' && m.text === 'reconciled')).toBe(
        true,
      ),
    );
    expect(apiGet).toHaveBeenCalledWith('/api/agent/threads/thread-1/messages', true);
  });

  it('sendMessage POSTs /turn not /messages', async () => {
    const { result } = renderHook(() =>
      useM2tAgent({
        threadId: 'thread-1',
        creatorId: 'creator-1',
        sessionContext: { sessionId: null, contextMode: 'both' },
      }),
    );

    await waitFor(() => expect(mockSockets.length).toBe(1));
    act(() => emitWs({ type: 'sidecar.ready', payload: { version: 'test' } }));
    await waitFor(() => expect(result.current.ready).toBe(true));

    await act(async () => {
      await result.current.sendMessage('hi there');
    });

    expect(apiPost).toHaveBeenCalledWith(
      '/api/agent/threads/thread-1/turn',
      { text: 'hi there', sidebarCreatorId: 'creator-1' },
      true,
    );
    expect(apiPost).not.toHaveBeenCalledWith(
      expect.stringContaining('/messages'),
      expect.anything(),
      expect.anything(),
    );
  });

  it('PATCHes activate on session context change', async () => {
    renderHook(() =>
      useM2tAgent({
        threadId: 'thread-1',
        creatorId: 'creator-1',
        threadCreatorId: 'creator-1',
        sessionContext: {
          sessionId: 'sess-9',
          sessionKind: 'vod',
          transcriptPath: 'creators/x/v.transcript.json',
          contextMode: 'transcript',
        },
      }),
    );

    await waitFor(() => {
      expect(apiPatch).toHaveBeenCalled();
      const [path, body] = apiPatch.mock.calls[0]!;
      expect(path).toBe('/api/agent/threads/thread-1/activate');
      expect(body).toMatchObject({
        creatorId: 'creator-1',
        sessionId: 'sess-9',
        sessionKind: 'vod',
        contextMode: 'transcript',
        transcriptPath: 'creators/x/v.transcript.json',
      });
    });
  });

  it('does not bind sidebar creator on global thread activate', async () => {
    renderHook(() =>
      useM2tAgent({
        threadId: 'thread-global',
        creatorId: 'creator-1',
        threadCreatorId: null,
        sessionContext: { sessionId: null, contextMode: 'both' },
      }),
    );

    await waitFor(() => {
      expect(apiPatch).toHaveBeenCalled();
      const [, body] = apiPatch.mock.calls[0]!;
      expect(body).not.toHaveProperty('creatorId');
    });
  });

  it('retryMessage POSTs /turn with retry flag and trims trailing messages', async () => {
    const { result } = renderHook(() =>
      useM2tAgent({
        threadId: 'thread-1',
        creatorId: 'creator-1',
        sessionContext: { sessionId: null, contextMode: 'both' },
      }),
    );

    await waitFor(() => expect(mockSockets.length).toBe(1));
    act(() => emitWs({ type: 'sidecar.ready', payload: { version: 'test' } }));
    await waitFor(() => expect(result.current.ready).toBe(true));
    await waitFor(() => expect(result.current.messages.some((m) => m.id === 'u1')).toBe(true));

    await act(async () => {
      await result.current.retryMessage('u1', 'hello');
    });

    expect(apiPost).toHaveBeenCalledWith(
      '/api/agent/threads/thread-1/turn',
      {
        text: 'hello',
        sidebarCreatorId: 'creator-1',
        retry: true,
        afterMessageId: 'u1',
      },
      true,
    );
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]?.id).toBe('u1');
  });

  it('shows toast on agent error event', async () => {
    const { result } = renderHook(() =>
      useM2tAgent({
        threadId: 'thread-1',
        creatorId: 'creator-1',
        sessionContext: { sessionId: null, contextMode: 'both' },
      }),
    );

    await waitFor(() => expect(mockSockets.length).toBe(1));
    act(() => emitWs({ type: 'sidecar.ready', payload: { version: 'test' } }));
    await waitFor(() => expect(result.current.ready).toBe(true));

    act(() => {
      emitWs({
        type: 'error',
        payload: { message: 'LLM API 认证失败', code: 'AGENT_ERROR' },
      });
    });

    expect(toast.showToast).toHaveBeenCalledWith('LLM API 认证失败', 'error');
  });

  it('appends tool.result messages from WS', async () => {
    const { result } = renderHook(() =>
      useM2tAgent({
        threadId: 'thread-1',
        creatorId: 'creator-1',
        sessionContext: { sessionId: null, contextMode: 'both' },
      }),
    );

    await waitFor(() => expect(mockSockets.length).toBe(1));
    act(() => emitWs({ type: 'sidecar.ready', payload: { version: 'test' } }));
    await waitFor(() => expect(result.current.status).toBe('ready'));

    act(() => {
      emitWs({
        type: 'tool.result',
        payload: { ok: true, data: { creators: [{ id: 'c1' }] } },
      });
    });

    await waitFor(() =>
      expect(result.current.messages.some((m) => m.role === 'tool')).toBe(true),
    );
  });
});
