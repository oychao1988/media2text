import flvjs from 'flv.js';
import { useEffect, useRef, useState } from 'react';
import { getApiBaseUrl } from '../../lib/api';
import { RecordBanner } from './RecordBanner';
import { StreamUnavailable } from './StreamUnavailable';

type Props = {
  creatorId: string | null;
  sessionId: string | null;
  attachStream?: boolean;
  visible?: boolean;
  showRecordBanner: boolean;
  onRecordingStarted?: () => void;
};

const FLV_LIVE_CONFIG: flvjs.Config = {
  enableStashBuffer: false,
  lazyLoad: false,
  autoCleanupSourceBuffer: true,
};

export function LivePlayer({
  creatorId,
  sessionId,
  attachStream = true,
  visible = true,
  showRecordBanner,
  onRecordingStarted,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<flvjs.Player | null>(null);
  const [loading, setLoading] = useState(false);
  const [streamError, setStreamError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  const shouldStream = Boolean(sessionId) && attachStream;
  const showIdlePlaceholder =
    !sessionId || (showRecordBanner && !loading && !streamError);

  useEffect(() => {
    if (!visible) return;
    const video = videoRef.current;
    if (!video) return;
    if (video.paused && playerRef.current) {
      void playerRef.current.play().catch(() => undefined);
    }
  }, [visible]);

  useEffect(() => {
    if (!shouldStream) {
      setLoading(false);
      setStreamError(false);
      if (playerRef.current) {
        playerRef.current.destroy();
        playerRef.current = null;
      }
      return undefined;
    }

    if (!flvjs.isSupported()) {
      setStreamError(true);
      setLoading(false);
      return undefined;
    }

    const video = videoRef.current;
    if (!video) return undefined;

    let cancelled = false;
    setLoading(true);
    setStreamError(false);

    const markReady = () => {
      if (!cancelled) setLoading(false);
    };

    const onVideoReady = () => markReady();
    video.addEventListener('loadeddata', onVideoReady);

    void (async () => {
      try {
        const base = await getApiBaseUrl();
        const url = `${base}/api/sessions/${sessionId}/stream/proxy`;
        if (cancelled) return;

        if (playerRef.current) {
          playerRef.current.destroy();
          playerRef.current = null;
        }

        const player = flvjs.createPlayer(
          { type: 'flv', url, isLive: true },
          FLV_LIVE_CONFIG,
        );
        player.attachMediaElement(video);
        player.on(flvjs.Events.MEDIA_INFO, markReady);
        player.on(flvjs.Events.ERROR, () => {
          if (!cancelled) {
            setStreamError(true);
            setLoading(false);
          }
        });

        player.load();
        video.muted = false;
        video.defaultMuted = false;
        try {
          await player.play();
        } catch {
          video.muted = true;
          try {
            await player.play();
            video.muted = false;
          } catch {
            /* user can press play in controls */
          }
        }

        if (!cancelled) {
          playerRef.current = player;
          markReady();
        } else {
          player.destroy();
        }
      } catch {
        if (!cancelled) {
          setStreamError(true);
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      video.removeEventListener('loadeddata', onVideoReady);
      if (playerRef.current) {
        playerRef.current.destroy();
        playerRef.current = null;
      }
    };
  }, [sessionId, retryKey, shouldStream]);

  return (
    <div className="video-area">
      <div className="video-viewport">
        <div className="video-frame">
          {shouldStream ? (
            <>
              <video
                ref={videoRef}
                className="live-video"
                controls
                autoPlay
                playsInline
              />
              {loading ? (
                <div className="video-overlay video-placeholder" aria-busy="true">
                  <div className="app-bootstrap-spinner" aria-hidden="true" />
                  <p>连接直播流…</p>
                </div>
              ) : null}
              {streamError && !loading ? (
                <div className="video-overlay">
                  <StreamUnavailable onRetry={() => setRetryKey((k) => k + 1)} />
                </div>
              ) : null}
            </>
          ) : showIdlePlaceholder ? (
            <div className="video-placeholder">
              <div className="play-icon" aria-hidden="true">
                ▶
              </div>
              <p>HTTP-FLV 直播预览</p>
              <p className="video-placeholder-hint">
                平台流经 API 反向代理 · 与 ffmpeg 录制并行
              </p>
            </div>
          ) : null}
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
