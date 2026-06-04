import flvjs from 'flv.js';
import { useEffect, useRef, useState } from 'react';
import { mediaUrl } from '../../lib/api';
import { showFlvBadge } from '../creators/creatorUtils';
import type { LiveSessionSummary } from '../../lib/types';
import { useLayoutStore } from '../layout/useLayoutStore';
import {
  formatSessionDuration,
  sessionPlaybackLabel,
  sessionSizeLabel,
} from './sessionDisplay';

type Props = {
  active?: boolean;
  creatorName: string;
  session: LiveSessionSummary | null;
};

export function ViewPlayback({ active, creatorName, session }: Props) {
  const { backToHistory } = useLayoutStore();
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<flvjs.Player | null>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState(false);

  const mediaPath = session?.media_path ?? session?.local_path ?? session?.temp_path ?? null;
  const isFlv = Boolean(mediaPath?.toLowerCase().endsWith('.flv'));
  const showBadge = showFlvBadge();

  useEffect(() => {
    if (!active) return undefined;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') backToHistory();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [active, backToHistory]);

  useEffect(() => {
    if (!mediaPath) {
      setSrc(null);
      return undefined;
    }
    let cancelled = false;
    void mediaUrl(mediaPath).then((url) => {
      if (!cancelled) setSrc(url);
    });
    return () => {
      cancelled = true;
    };
  }, [mediaPath]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src || !active) return undefined;

    setError(false);
    if (isFlv && flvjs.isSupported()) {
      const player = flvjs.createPlayer({ type: 'flv', url: src });
      player.attachMediaElement(video);
      player.load();
      player.play().catch(() => undefined);
      player.on(flvjs.Events.ERROR, () => setError(true));
      playerRef.current = player;
      return () => {
        player.destroy();
        playerRef.current = null;
      };
    }

    video.src = src;
    try {
      video.load();
    } catch {
      /* jsdom lacks HTMLMediaElement.load */
    }
    return undefined;
  }, [src, isFlv, active]);

  const duration = session ? formatSessionDuration(session.started_at, session.ended_at) : null;
  const breadcrumb = session ? sessionPlaybackLabel(session) : '—';
  const badgeText = mediaPath
    ? `<video> · GET /api/media?path=…`
    : '无媒体文件';

  return (
    <div className={`center-view${active ? ' active' : ''}`} id="view-playback">
      <div className="breadcrumb-bar">
        <button type="button" id="back-to-history" onClick={backToHistory}>
          ← 返回列表
        </button>
        <span className="sep">›</span>
        <span>{creatorName || '—'}</span>
        <span className="sep">›</span>
        <span className="current" id="playback-breadcrumb">
          {breadcrumb}
        </span>
      </div>
      {session ? (
        <div className="playback-meta" id="playback-meta">
          <span>session {session.session_id}</span>
          {duration ? <span>{duration}</span> : null}
          <span>{sessionSizeLabel(session)}</span>
          {mediaPath ? <span>{mediaPath}</span> : null}
        </div>
      ) : null}
      <div className="video-area playback-video-area">
        <div className="video-viewport">
          <div className="video-frame">
            <div className="video-overlay-top">
              {showBadge ? <span className="flv-badge">{badgeText}</span> : null}
            </div>
            {!session || !mediaPath ? (
              <div className="video-placeholder">
                <div className="play-icon" aria-hidden="true">
                  ▶
                </div>
                <p>历史录播 · MP4</p>
                <p className="video-placeholder-hint">选择历史场次以回放</p>
              </div>
            ) : error ? (
              <p className="hint">回放加载失败</p>
            ) : (
              <video ref={videoRef} className="history-video" controls playsInline />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
