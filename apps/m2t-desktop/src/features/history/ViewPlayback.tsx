import flvjs from 'flv.js';
import { useEffect, useRef, useState } from 'react';
import { mediaUrl } from '../../lib/api';
import type { LiveSessionSummary } from '../../lib/types';
import { useLayoutStore } from '../layout/useLayoutStore';
import {
  sessionMediaMissing,
  sessionMediaPath,
  sessionPlaybackLabel,
  sessionCloudAvailable,
} from './sessionDisplay';

type Props = {
  active?: boolean;
  creatorName: string;
  session: LiveSessionSummary | null;
  onTimeUpdate?: (time: number) => void;
};

export function ViewPlayback({ active, creatorName, session, onTimeUpdate }: Props) {
  const { backToHistory } = useLayoutStore();
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<flvjs.Player | null>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState(false);

  const mediaPath = session ? sessionMediaPath(session) : null;
  const mediaMissing = session ? sessionMediaMissing(session) : false;
  const canPlay = Boolean(mediaPath && session?.media_available && !mediaMissing);
  const isFlv = Boolean(mediaPath?.toLowerCase().endsWith('.flv'));

  useEffect(() => {
    if (!active) return undefined;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') backToHistory();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [active, backToHistory]);

  useEffect(() => {
    if (!canPlay || !mediaPath) {
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
  }, [mediaPath, canPlay]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src || !active || !canPlay) return undefined;

    setError(false);
    const onVideoError = () => setError(true);
    video.addEventListener('error', onVideoError);

    // timeupdate → 通知外部同步转写滚动
    const handleVideoTimeUpdate = () => {
      if (onTimeUpdate) {
        console.log('[playback] timeupdate:', video.currentTime);
        onTimeUpdate(video.currentTime);
      }
    };
    video.addEventListener('timeupdate', handleVideoTimeUpdate);

    if (isFlv && flvjs.isSupported()) {
      const player = flvjs.createPlayer({ type: 'flv', url: src });
      player.attachMediaElement(video);
      player.load();
      player.play().catch(() => undefined);
      player.on(flvjs.Events.ERROR, () => setError(true));
      playerRef.current = player;
      return () => {
        video.removeEventListener('error', onVideoError);
        video.removeEventListener('timeupdate', handleVideoTimeUpdate);
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
    return () => {
      video.removeEventListener('error', onVideoError);
      video.removeEventListener('timeupdate', handleVideoTimeUpdate);
    };
  }, [src, isFlv, active, canPlay, onTimeUpdate]);

  const breadcrumb = session ? sessionPlaybackLabel(session) : '—';
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
      <div className="video-area playback-video-area">
        <div className="video-viewport">
          <div className="video-frame">
            {!session || !mediaPath ? (
              <div className="video-placeholder">
                <div className="play-icon" aria-hidden="true">
                  ▶
                </div>
                <p>历史录播</p>
                <p className="video-placeholder-hint">选择历史场次以回放</p>
              </div>
            ) : mediaMissing || !session.media_available ? (
              <div className="video-placeholder">
                <p>视频文件缺失</p>
                <p className="video-placeholder-hint">
                  {sessionCloudAvailable(session)
                    ? '本地文件已删除，可在历史列表从云端下载'
                    : '录制路径存在但文件不可用，仍可查看转写与摘要'}
                </p>
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
