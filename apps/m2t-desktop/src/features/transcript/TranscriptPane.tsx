import { useEffect, useReducer, useState, type CSSProperties } from 'react';
import ReactMarkdown from 'react-markdown';
import { apiGet, buildWsUrl, getApiBaseUrl } from '../../lib/api';
import { showToast } from '../../lib/toast';
import type { TranscriptPayload } from '../../lib/types';
import {
  formatTs,
  initialTranscriptState,
  transcriptReducer,
  type TranscriptViewState,
} from './transcriptReducer';

type Props = {
  sessionId: string | null;
  summaryPath: string | null;
  mode?: 'live' | 'playback';
};

function paneDisplay(visible: boolean): CSSProperties | undefined {
  return visible ? undefined : { display: 'none' };
}

function TranscriptContent({
  state,
  sessionId,
}: {
  state: TranscriptViewState;
  sessionId: string | null;
}) {
  return (
    <>
      {state.loading ? (
        <p className="hint">加载转写…</p>
      ) : state.waiting ? (
        <p style={{ color: 'var(--text-dim)', fontSize: 12, marginBottom: 12 }}>
          {sessionId
            ? '等待转写…'
            : '未开始录制 — 开录后此处通过 WebSocket 推送 partial 转写。'}
        </p>
      ) : null}
      {state.partial && !state.waiting ? (
        <p className="partial-hint">实时转写（partial）</p>
      ) : null}
      {state.segments.length
        ? state.segments.map((seg, i) => (
            <div className="seg" key={`${seg.start}-${i}`}>
              <div className="ts">{formatTs(seg.start)}</div>
              <div>{seg.text}</div>
            </div>
          ))
        : state.text
          ? (
              <div className="seg">
                <div className="ts">—</div>
                <div>{state.text}</div>
              </div>
            )
          : null}
    </>
  );
}

export function TranscriptPane({ sessionId, summaryPath, mode = 'live' }: Props) {
  const [tab, setTab] = useState<'transcript' | 'summary'>('transcript');
  const [state, dispatch] = useReducer(transcriptReducer, initialTranscriptState);
  const [summaryMd, setSummaryMd] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  const isPlayback = mode === 'playback';
  const showLiveTranscript = !isPlayback && tab === 'transcript';
  const showPlaybackTranscript = isPlayback && tab === 'transcript';
  const showSummaryPlayback = tab === 'summary';

  useEffect(() => {
    dispatch({ type: 'reset' });
    setSummaryMd(null);
    if (!sessionId) {
      dispatch({ type: 'waiting', value: true });
      return undefined;
    }

    let cancelled = false;
    let ws: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let attempt = 0;

    const applyPayload = (payload: TranscriptPayload) => {
      if (!cancelled) dispatch({ type: 'payload', payload });
    };

    const loadRest = async () => {
      try {
        const res = await apiGet<TranscriptPayload & { ok: boolean }>(
          `/api/sessions/${sessionId}/transcript`,
          true,
        );
        if (!cancelled) applyPayload(res);
      } catch {
        if (!cancelled) dispatch({ type: 'waiting', value: true });
      }
    };

    const connectWs = async () => {
      if (cancelled) return;
      try {
        const url = await buildWsUrl(`/api/sessions/${sessionId}/transcript/stream`);
        ws = new WebSocket(url);
      } catch {
        dispatch({ type: 'disconnected', value: true });
        scheduleReconnect();
        return;
      }

      ws.onopen = () => {
        attempt = 0;
        dispatch({ type: 'disconnected', value: false });
      };

      ws.onmessage = (ev) => {
        try {
          applyPayload(JSON.parse(String(ev.data)) as TranscriptPayload);
        } catch {
          /* ignore */
        }
      };

      ws.onclose = () => {
        if (!cancelled) {
          dispatch({ type: 'disconnected', value: true });
          scheduleReconnect();
        }
      };

      ws.onerror = () => ws?.close();
    };

    const scheduleReconnect = () => {
      if (cancelled) return;
      const delay = Math.min(1000 * 2 ** attempt, 30000);
      attempt += 1;
      reconnectTimer = window.setTimeout(() => {
        void loadRest();
        void connectWs();
      }, delay);
    };

    void loadRest();
    if (mode === 'live') void connectWs();

    return () => {
      cancelled = true;
      if (reconnectTimer != null) window.clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [sessionId, mode]);

  useEffect(() => {
    if (tab !== 'summary' || !summaryPath) return;
    let cancelled = false;
    setSummaryLoading(true);
    void (async () => {
      try {
        const base = await getApiBaseUrl();
        const q = new URLSearchParams({ path: summaryPath });
        const res = await fetch(`${base}/api/media?${q.toString()}`);
        if (!res.ok) throw new Error('摘要不可用');
        const text = await res.text();
        if (!cancelled) setSummaryMd(text);
      } catch {
        if (!cancelled) setSummaryMd(null);
      } finally {
        if (!cancelled) setSummaryLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tab, summaryPath]);

  const copyTranscript = async () => {
    const text = state.text || state.segments.map((s) => s.text).join('\n');
    if (!text.trim()) {
      showToast('暂无转写内容', 'info');
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      showToast('已复制转写', 'success');
    } catch {
      showToast('复制失败', 'error');
    }
  };

  return (
    <section className="transcript-pane" aria-label="转写">
      <div className="tab-row" role="tablist">
        <button
          className={`tab${tab === 'transcript' ? ' active' : ''}`}
          role="tab"
          type="button"
          aria-selected={tab === 'transcript'}
          onClick={() => setTab('transcript')}
        >
          转写
        </button>
        <button
          className={`tab${tab === 'summary' ? ' active' : ''}`}
          role="tab"
          type="button"
          aria-selected={tab === 'summary'}
          onClick={() => setTab('summary')}
        >
          摘要
        </button>
        <button
          className="btn"
          type="button"
          id="btn-copy-transcript"
          style={{ marginLeft: 'auto', padding: '4px 8px', fontSize: 11 }}
          onClick={() => void copyTranscript()}
        >
          复制
        </button>
      </div>

      {state.disconnected && showLiveTranscript ? (
        <div className="transcript-banner warn" role="status">
          转写连接已断开，正在重连…
        </div>
      ) : null}

      <div className="transcript-body" id="transcript-body">
        <div id="transcript-live" style={paneDisplay(showLiveTranscript)}>
          <TranscriptContent state={state} sessionId={sessionId} />
        </div>
        <div id="transcript-playback" style={paneDisplay(showPlaybackTranscript)}>
          <TranscriptContent state={state} sessionId={sessionId} />
        </div>
        <div
          id="summary-playback"
          className="summary-preview"
          style={paneDisplay(showSummaryPlayback)}
        >
          {summaryLoading ? (
            <p className="hint">加载摘要…</p>
          ) : summaryMd ? (
            <ReactMarkdown>{summaryMd}</ReactMarkdown>
          ) : (
            <p className="hint">{summaryPath ? '暂无摘要' : '选择有摘要的场次以查看'}</p>
          )}
        </div>
      </div>
    </section>
  );
}
