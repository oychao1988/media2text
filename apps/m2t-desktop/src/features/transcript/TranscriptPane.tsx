import {
  useCallback,
  useEffect,
  useReducer,
  useRef,
  useState,
  type CSSProperties,
} from 'react';
import ReactMarkdown from 'react-markdown';
import { apiGet, apiPost, buildWsUrl, mediaUrl } from '../../lib/api';
import { showToast } from '../../lib/toast';
import type { TranscriptPayload } from '../../lib/types';
import { TranscriptSessionSelect } from './TranscriptSessionSelect';
import {
  formatTs,
  initialTranscriptState,
  transcriptReducer,
  type TranscriptViewState,
} from './transcriptReducer';

type Props = {
  sessionId: string | null;
  summaryPath: string | null;
  transcriptPath?: string | null;
  mode?: 'live' | 'playback';
  playbackTime?: number;
  playbackItem?: {
    creatorId: string;
    kind: 'live' | 'vod';
    itemId: string;
    hasTranscript: boolean;
    hasSummary: boolean;
  } | null;
  onSummaryUpdated?: (summaryPath: string | null) => void;
};

const LIVE_SCROLL_TAIL_PX = 48;

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
            <div className="seg" key={`${seg.start}-${i}`} data-seg-idx={i}>
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

export function TranscriptPane({
  sessionId,
  summaryPath,
  transcriptPath = null,
  mode = 'live',
  playbackTime = 0,
  playbackItem = null,
  onSummaryUpdated,
}: Props) {
  const [tab, setTab] = useState<'transcript' | 'summary'>('transcript');
  const [state, dispatch] = useReducer(transcriptReducer, initialTranscriptState);
  const [summaryMd, setSummaryMd] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryBusy, setSummaryBusy] = useState(false);
  const [activeSummaryPath, setActiveSummaryPath] = useState<string | null>(summaryPath);
  const bodyRef = useRef<HTMLDivElement>(null);
  const followLiveRef = useRef(true);
  const followPlaybackRef = useRef(true);

  const isPlayback = mode === 'playback';
  const showLiveTranscript = !isPlayback && tab === 'transcript';
  const showPlaybackTranscript = isPlayback && tab === 'transcript';
  const showSummaryPlayback = tab === 'summary';

  useEffect(() => {
    setActiveSummaryPath(summaryPath);
  }, [summaryPath]);

  useEffect(() => {
    followLiveRef.current = true;
  }, [sessionId]);

  useEffect(() => {
    if (mode !== 'live' || tab !== 'transcript' || !followLiveRef.current) return;
    const el = bodyRef.current;
    if (!el) return;
    const id = requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
    return () => cancelAnimationFrame(id);
  }, [
    mode,
    tab,
    state.segments,
    state.text,
    state.waiting,
    state.loading,
    state.partial,
  ]);

  // Playback 模式：根据视频时间同步滚动转写
  useEffect(() => {
    console.log('[transcript] playback effect:', {
      isPlayback,
      tab,
      followCurrent: followPlaybackRef.current,
      segmentsLen: state.segments.length,
      playbackTime,
    });
    if (!isPlayback || tab !== 'transcript' || !followPlaybackRef.current) return;
    if (!state.segments.length) return;
    const el = bodyRef.current;
    if (!el) {
      console.log('[transcript] bodyRef el is null');
      return;
    }

    // 找到当前时间对应的 segment（兼容起始时刻无匹配的情况）
    let segIdx = state.segments.findIndex((s) => s.start <= playbackTime && s.end >= playbackTime);
    // 起始时刻（playbackTime < 第一个 segment.start）时，找最后一个 start <= playbackTime 的
    if (segIdx < 0) {
      segIdx = state.segments.reduce((best, s, i) => (s.start <= playbackTime && s.start > (state.segments[best]?.start ?? -Infinity) ? i : best), -1);
    }
    console.log('[transcript] segIdx:', segIdx, 'playbackTime:', playbackTime);
    if (segIdx < 0) return;

    const segEl = el.querySelector(`[data-seg-idx="${segIdx}"]`);
    console.log('[transcript] segEl:', segEl);
    if (!segEl) return;

    const elTop = el.getBoundingClientRect().top;
    const segTop = segEl.getBoundingClientRect().top;
    const offset = segTop - elTop + el.scrollTop - el.clientHeight / 4;
    el.scrollTop = Math.max(0, offset);
  }, [isPlayback, tab, playbackTime, state.segments]);

  const handleBodyScroll = useCallback(() => {
    if (mode !== 'live' && mode !== 'playback' && tab !== 'transcript') return;
    const el = bodyRef.current;
    if (!el) return;
    if (mode === 'live') {
      const tail = el.scrollHeight - el.scrollTop - el.clientHeight;
      followLiveRef.current = tail <= LIVE_SCROLL_TAIL_PX;
    }
    if (mode === 'playback' && tab === 'transcript' && state.segments.length) {
      // 用户手动滚动到离当前播放位置较远时停止跟随
      const segIdx = state.segments.findIndex((s) => s.start <= playbackTime && s.end >= playbackTime);
      if (segIdx < 0) return;
      const segEl = el.querySelector(`[data-seg-idx="${segIdx}"]`);
      if (!segEl) return;
      const elTop = el.getBoundingClientRect().top;
      const segTop = segEl.getBoundingClientRect().top;
      const segCenterOffset = Math.abs(segTop - elTop + el.scrollTop - el.clientHeight / 2);
      // 滚动后当前 segment 中心偏离视口中心超过 1/3 屏则认为用户主动滚动
      followPlaybackRef.current = segCenterOffset < el.clientHeight / 3;
    }
  }, [mode, tab, playbackTime, state.segments]);

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
        if (mode === 'playback' && playbackItem) {
          if (transcriptPath) {
            const url = await mediaUrl(transcriptPath);
            const res = await fetch(url);
            if (!res.ok) throw new Error('transcript unavailable');
            const payload = (await res.json()) as TranscriptPayload;
            if (!cancelled) applyPayload(payload);
            return;
          }
          const res = await apiGet<TranscriptPayload & { ok: boolean }>(
            `/api/creators/${playbackItem.creatorId}/history/${playbackItem.kind}/${playbackItem.itemId}/transcript`,
            true,
          );
          if (!cancelled) applyPayload(res);
          return;
        }
        if (mode === 'playback' && transcriptPath) {
          const url = await mediaUrl(transcriptPath);
          const res = await fetch(url);
          if (!res.ok) throw new Error('transcript unavailable');
          const payload = (await res.json()) as TranscriptPayload;
          if (!cancelled) applyPayload(payload);
          return;
        }
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
  }, [sessionId, transcriptPath, mode, playbackItem]);

  useEffect(() => {
    if (tab !== 'summary') return;
    if (!sessionId && !activeSummaryPath) return;
    let cancelled = false;
    setSummaryLoading(true);
    setSummaryMd(null);
    void (async () => {
      try {
        if (mode === 'playback' && playbackItem) {
          if (activeSummaryPath) {
            const url = await mediaUrl(activeSummaryPath);
            const res = await fetch(url);
            if (!res.ok) throw new Error('摘要不可用');
            const text = await res.text();
            if (!cancelled) setSummaryMd(text.trim() ? text : null);
            return;
          }
          const res = await apiGet<{ ok: boolean; text: string }>(
            `/api/creators/${playbackItem.creatorId}/history/${playbackItem.kind}/${playbackItem.itemId}/summary`,
            true,
          );
          if (!cancelled) setSummaryMd(res.text?.trim() ? res.text : null);
          return;
        }
        if (mode === 'playback' && activeSummaryPath) {
          const url = await mediaUrl(activeSummaryPath);
          const res = await fetch(url);
          if (!res.ok) throw new Error('摘要不可用');
          const text = await res.text();
          if (!cancelled) setSummaryMd(text.trim() ? text : null);
          return;
        }
        if (mode === 'playback' && sessionId) {
          const res = await apiGet<{ ok: boolean; text: string }>(
            `/api/sessions/${sessionId}/summary`,
            true,
          );
          if (!cancelled) setSummaryMd(res.text?.trim() ? res.text : null);
          return;
        }
        if (!activeSummaryPath) {
          if (!cancelled) setSummaryMd(null);
          return;
        }
        const url = await mediaUrl(activeSummaryPath);
        const res = await fetch(url);
        if (!res.ok) throw new Error('摘要不可用');
        const text = await res.text();
        if (!cancelled) setSummaryMd(text.trim() ? text : null);
      } catch {
        if (!cancelled) setSummaryMd(null);
      } finally {
        if (!cancelled) setSummaryLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tab, activeSummaryPath, sessionId, mode, playbackItem]);

  const canSummarize =
    mode === 'playback' && playbackItem != null && playbackItem.hasTranscript;

  const runSummarize = async (force: boolean) => {
    if (!playbackItem || summaryBusy) return;
    setSummaryBusy(true);
    try {
      const res = await apiPost<{
        ok: boolean;
        skipped?: boolean;
        summary_path?: string | null;
        detail?: string;
        error?: string;
      }>(
        `/api/creators/${playbackItem.creatorId}/history/${playbackItem.kind}/${playbackItem.itemId}/summarize?force=${force ? 'true' : 'false'}`,
        undefined,
        true,
      );
      const nextPath = res.summary_path ?? activeSummaryPath;
      setActiveSummaryPath(nextPath);
      onSummaryUpdated?.(nextPath);
      if (nextPath) {
        const url = await mediaUrl(nextPath);
        const textRes = await fetch(url);
        if (textRes.ok) {
          const text = await textRes.text();
          setSummaryMd(text.trim() ? text : null);
        }
      }
      if (res.skipped) {
        showToast('摘要已存在', 'info');
      } else {
        showToast(force ? '摘要已重新生成' : '摘要已生成', 'success');
      }
      setTab('summary');
    } catch (err) {
      const msg = err instanceof Error ? err.message : '摘要生成失败';
      showToast(
        msg.includes('404') || msg === 'Not Found'
          ? 'API 版本过旧，请完全退出并重启 Desktop（或 dev 下重启 tauri dev）'
          : msg,
        'error',
      );
    } finally {
      setSummaryBusy(false);
    }
  };

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
        <div className="transcript-tab-actions">
          <TranscriptSessionSelect />
          <button
            className="btn"
            type="button"
            id="btn-copy-transcript"
            style={{ padding: '4px 8px', fontSize: 11 }}
            onClick={() => void copyTranscript()}
          >
            复制
          </button>
          {canSummarize ? (
            <button
              className="btn"
              type="button"
              style={{ padding: '4px 8px', fontSize: 11 }}
              disabled={summaryBusy}
              onClick={() => void runSummarize(Boolean(playbackItem?.hasSummary || summaryMd))}
            >
              {summaryBusy ? '生成中…' : playbackItem?.hasSummary || summaryMd ? '重新摘要' : '生成摘要'}
            </button>
          ) : null}
        </div>
      </div>

      {state.disconnected && showLiveTranscript ? (
        <div className="transcript-banner warn" role="status">
          转写连接已断开，正在重连…
        </div>
      ) : null}

      <div
        className="transcript-body"
        id="transcript-body"
        ref={bodyRef}
        onScroll={handleBodyScroll}
      >
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
            <>
              <p className="hint">
                {activeSummaryPath || sessionId
                  ? '暂无摘要'
                  : '选择有摘要的场次以查看'}
              </p>
              {canSummarize ? (
                <button
                  className="btn"
                  type="button"
                  disabled={summaryBusy}
                  onClick={() => void runSummarize(false)}
                >
                  {summaryBusy ? '生成中…' : '生成摘要'}
                </button>
              ) : null}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
