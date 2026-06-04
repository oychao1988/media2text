import flvjs from 'flv.js';
import { useEffect, useRef, useState } from 'react';
import { getApiBaseUrl } from '../../lib/api';
import { showFlvBadge } from '../creators/creatorUtils';
import { RecordBanner } from './RecordBanner';
import { StreamUnavailable } from './StreamUnavailable';

type Props = {
  creatorId: string | null;
  sessionId: string | null;
  showRecordBanner: boolean;
  onRecordingStarted?: () => void;
};

export function LivePlayer({
  creatorId,
  sessionId,
  showRecordBanner,
  onRecordingStarted,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<flvjs.Player | null>(null);
  const [loading, setLoading] = useState(false);
  const [streamError, setStreamError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !sessionId) {
      if (playerRef.current) {
        playerRef.current.destroy();
        playerRef.current = null;
      }
      return undefined;
    }

    if (!flvjs.isSupported()) {
      setStreamError(true);
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setStreamError(false);

    void (async () => {
      try {
        const base = await getApiBaseUrl();
        const url = `${base}/api/sessions/${sessionId}/stream/proxy`;
        if (cancelled) return;

        if (playerRef.current) {
          playerRef.current.destroy();
          playerRef.current = null;
        }

        const player = flvjs.createPlayer({ type: 'flv', url, isLive: true });
        player.attachMediaElement(video);
        player.load();
        player.play().catch(() => {
          /* autoplay may fail */
        });

        player.on(flvjs.Events.ERROR, () => {
          if (!cancelled) setStreamError(true);
        });

        playerRef.current = player;
        setLoading(false);
      } catch {
        if (!cancelled) {
          setStreamError(true);
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      if (playerRef.current) {
        playerRef.current.destroy();
        playerRef.current = null;
      }
    };
  }, [sessionId, retryKey]);

  const showBadge = showFlvBadge();
  const flvHint = sessionId
    ? `flv.js · /api/sessions/${sessionId}/stream/proxy`
    : 'flv.js · /api/sessions/…/stream/proxy';

  const showPlaceholder = !sessionId || (showRecordBanner && !loading && !streamError);

  return (
    <div className="video-area">
      <div className="video-viewport">
        <div className="video-frame">
          <div className="video-overlay-top">
            {showBadge ? <span className="flv-badge">{flvHint}</span> : null}
          </div>
          {loading ? (
            <div className="video-placeholder">
              <div className="app-bootstrap-spinner" aria-hidden="true" />
              <p>连接直播流…</p>
            </div>
          ) : showPlaceholder ? (
            <div className="video-placeholder">
              <div className="play-icon" aria-hidden="true">
                ▶
              </div>
              <p>HTTP-FLV 直播预览</p>
              <p className="video-placeholder-hint">
                平台流经 API 反向代理 · 与 ffmpeg 录制并行
              </p>
            </div>
          ) : streamError ? (
            <StreamUnavailable onRetry={() => setRetryKey((k) => k + 1)} />
          ) : (
            <video ref={videoRef} className="live-video" controls muted playsInline />
          )}
        </div>
      </div>
      {creatorId ? (
        <RecordBanner
          creatorId={creatorId}
          visible={showRecordBanner}
          onStarted={onRecordingStarted}
        />
      ) : null}
    </div>
  );
}
