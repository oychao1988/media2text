import flvjs from 'flv.js';
import { useEffect, useRef, useState } from 'react';
import { getApiBaseUrl } from '../../lib/api';
import { releaseLiveFlvPlayer } from './liveFlvPlayer';
import { RecordBanner } from './RecordBanner';
import { StreamUnavailable } from './StreamUnavailable';

type Props = {
  creatorId: string | null;
  sessionId: string | null;
  attachStream?: boolean;
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
  showRecordBanner,
  onRecordingStarted,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<flvjs.Player | null>(null);
  const generationRef = useRef(0);
  const [loading, setLoading] = useState(false);
  const [streamError, setStreamError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  const shouldStream = Boolean(sessionId) && attachStream;
  const showIdlePlaceholder =
    !sessionId || (showRecordBanner && !loading && !streamError);

  useEffect(() => {
    const video = videoRef.current;
    if (!shouldStream) {
      setLoading(false);
      setStreamError(false);
      generationRef.current += 1;
      releaseLiveFlvPlayer(video, playerRef);
      return undefined;
    }

    if (!flvjs.isSupported()) {
      setStreamError(true);
      setLoading(false);
      return undefined;
    }

    if (!video) return undefined;

    const generation = ++generationRef.current;
    setLoading(true);
    setStreamError(false);

    const markReady = () => {
      if (generation === generationRef.current) setLoading(false);
    };

    const onVideoReady = () => markReady();
    video.addEventListener('loadeddata', onVideoReady);
    releaseLiveFlvPlayer(video, playerRef);

    void (async () => {
      try {
        const base = await getApiBaseUrl();
        if (generation !== generationRef.current) return;

        const url = `${base}/api/sessions/${sessionId}/stream/proxy`;
        const player = flvjs.createPlayer(
          { type: 'flv', url, isLive: true },
          FLV_LIVE_CONFIG,
        );
        player.attachMediaElement(video);
        player.on(flvjs.Events.MEDIA_INFO, markReady);
        player.on(flvjs.Events.ERROR, () => {
          if (generation === generationRef.current) {
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

        if (generation !== generationRef.current) {
          releaseLiveFlvPlayer(video, { current: player });
          return;
        }
        playerRef.current = player;
        markReady();
      } catch {
        if (generation === generationRef.current) {
          setStreamError(true);
          setLoading(false);
        }
      }
    })();

    return () => {
      generationRef.current += 1;
      video.removeEventListener('loadeddata', onVideoReady);
      releaseLiveFlvPlayer(video, playerRef);
    };
  }, [sessionId, retryKey, shouldStream]);

  return (
    <div className="video-area">
      <div className="video-viewport">
        <div className="video-frame">
          {shouldStream ? (
            <>
              <video ref={videoRef} className="live-video" controls playsInline />
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
