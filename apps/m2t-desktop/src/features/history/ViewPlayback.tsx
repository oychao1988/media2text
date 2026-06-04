import flvjs from 'flv.js';
import { useEffect, useRef, useState } from 'react';
import { mediaUrl } from '../../lib/api';

type Props = {
  mediaPath: string | null;
};

export function ViewPlayback({ mediaPath }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const playerRef = useRef<flvjs.Player | null>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState(false);

  const isFlv = Boolean(mediaPath?.toLowerCase().endsWith('.flv'));

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
    if (!video || !src) return undefined;

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
    video.load();
    return undefined;
  }, [src, isFlv]);

  if (!mediaPath) {
    return (
      <div className="history-playback-empty">
        <p className="hint">选择历史场次以回放</p>
      </div>
    );
  }

  if (error) {
    return <p className="hint">回放加载失败</p>;
  }

  return (
    <div className="history-playback">
      <video ref={videoRef} className="history-video" controls playsInline />
    </div>
  );
}
