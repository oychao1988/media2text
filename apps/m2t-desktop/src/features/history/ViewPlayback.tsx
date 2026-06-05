import flvjs from 'flv.js';
import { useEffect, useRef, useState } from 'react';
import { listGalleryImages, mediaUrl } from '../../lib/api';
import type { LiveSessionSummary } from '../../lib/types';
import { useLayoutStore } from '../layout/useLayoutStore';
import {
  sessionIsGallery,
  sessionIsListedPending,
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

function GalleryPlayback({ dirPath, active }: { dirPath: string; active?: boolean }) {
  const [images, setImages] = useState<string[]>([]);
  const [urls, setUrls] = useState<string[]>([]);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    void (async () => {
      try {
        const res = await listGalleryImages(dirPath);
        const list = res.images ?? [];
        if (cancelled) return;
        setImages(list);
        setIndex(0);
        if (!list.length) {
          setError(true);
          return;
        }
        const resolved = await Promise.all(list.map((p) => mediaUrl(p)));
        if (!cancelled) setUrls(resolved);
      } catch {
        if (!cancelled) setError(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [dirPath, active]);

  if (error || !urls.length) {
    return <p className="hint">图集加载失败</p>;
  }

  const at = Math.min(index, urls.length - 1);
  return (
    <div className="gallery-viewer">
      <img
        src={urls[at]}
        alt={`图 ${at + 1} / ${urls.length}`}
        className="gallery-image"
      />
      {urls.length > 1 ? (
        <div className="gallery-controls">
          <button
            type="button"
            className="btn btn-sm"
            disabled={at <= 0}
            onClick={() => setIndex((i) => Math.max(0, i - 1))}
          >
            上一张
          </button>
          <span className="gallery-counter">
            {at + 1} / {urls.length}
          </span>
          <button
            type="button"
            className="btn btn-sm"
            disabled={at >= urls.length - 1}
            onClick={() => setIndex((i) => Math.min(urls.length - 1, i + 1))}
          >
            下一张
          </button>
        </div>
      ) : null}
      {images.length > 1 ? (
        <div className="gallery-thumbs" role="list">
          {urls.map((url, i) => (
            <button
              key={images[i]}
              type="button"
              className={`gallery-thumb${i === at ? ' active' : ''}`}
              onClick={() => setIndex(i)}
            >
              <img src={url} alt="" />
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function ViewPlayback({ active, creatorName, session, onTimeUpdate }: Props) {
  const { backToHistory } = useLayoutStore();
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<flvjs.Player | null>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState(false);

  const mediaPath = session ? sessionMediaPath(session) : null;
  const mediaMissing = session ? sessionMediaMissing(session) : false;
  const isGallery = session ? sessionIsGallery(session) : false;
  const isListed = session ? sessionIsListedPending(session) : false;
  const canPlayVideo = Boolean(
    mediaPath && session?.media_available && !mediaMissing && !isGallery && !isListed,
  );
  const canShowGallery = Boolean(
    mediaPath && session?.media_available && !mediaMissing && isGallery,
  );
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
    if (!canPlayVideo || !mediaPath) {
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
  }, [mediaPath, canPlayVideo]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src || !active || !canPlayVideo) return undefined;

    setError(false);
    const onVideoError = () => setError(true);
    video.addEventListener('error', onVideoError);

    const handleVideoTimeUpdate = () => {
      if (onTimeUpdate) {
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
  }, [src, isFlv, active, canPlayVideo, onTimeUpdate]);

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
            {!session ? (
              <div className="video-placeholder">
                <div className="play-icon" aria-hidden="true">
                  ▶
                </div>
                <p>历史录播</p>
                <p className="video-placeholder-hint">选择历史场次以回放</p>
              </div>
            ) : isListed ? (
              <div className="video-placeholder">
                <p>作品待下载</p>
                <p className="video-placeholder-hint">
                  请在「管理」页使用「同步并下载」或「下载作品」，并确保监控已开启
                </p>
              </div>
            ) : canShowGallery && mediaPath ? (
              <GalleryPlayback dirPath={mediaPath} active={active} />
            ) : !mediaPath ? (
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
