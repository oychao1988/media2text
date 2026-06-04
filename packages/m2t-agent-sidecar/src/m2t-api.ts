import type { ToolResultPayload } from '@m2t/shared';

export type M2tApiClientOptions = {
  baseUrl: string;
};

function extractError(data: unknown, status: number): string {
  if (typeof data === 'string' && data.trim()) return data;
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if (typeof obj.detail === 'string') return obj.detail;
    if (obj.detail && typeof obj.detail === 'object') {
      const d = obj.detail as Record<string, unknown>;
      if (typeof d.error === 'string') return d.error;
      if (typeof d.message === 'string') return d.message;
    }
    if (typeof obj.error === 'string') return obj.error;
    if (typeof obj.message === 'string') return obj.message;
  }
  return `HTTP ${status}`;
}

export class M2tApiClient {
  private readonly baseUrl: string;

  constructor(opts: M2tApiClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/$/, '');
  }

  async request(method: string, path: string, body?: unknown): Promise<ToolResultPayload> {
    const url = `${this.baseUrl}${path.startsWith('/') ? path : `/${path}`}`;
    try {
      const res = await fetch(url, {
        method,
        headers: body != null ? { 'Content-Type': 'application/json' } : undefined,
        body: body != null ? JSON.stringify(body) : undefined,
      });
      let data: unknown = null;
      const ct = res.headers.get('content-type') ?? '';
      if (ct.includes('application/json')) {
        try {
          data = await res.json();
        } catch {
          data = null;
        }
      } else if (!res.ok) {
        data = await res.text().catch(() => null);
      }
      if (!res.ok) {
        return {
          ok: false,
          error: {
            code: String(res.status),
            message: extractError(data, res.status),
          },
        };
      }
      const record = (data ?? {}) as Record<string, unknown>;
      if (record.ok === false) {
        return {
          ok: false,
          error: {
            code: 'API_ERROR',
            message: extractError(record, res.status),
          },
        };
      }
      return {
        ok: true,
        data: record,
        ui: { kind: 'text', payload: { message: '完成' } },
      };
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return {
        ok: false,
        error: { code: 'NETWORK', message },
      };
    }
  }
}
