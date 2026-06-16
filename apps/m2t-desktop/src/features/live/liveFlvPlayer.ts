import type { MutableRefObject } from 'react';
import flvjs from 'flv.js';

/** Tear down flv.js + <video> so no hidden decode/audio survives tab switches or StrictMode remounts. */
export function releaseLiveFlvPlayer(
  video: HTMLVideoElement | null,
  playerRef: MutableRefObject<flvjs.Player | null>,
) {
  const player = playerRef.current;
  playerRef.current = null;
  if (player) {
    try {
      player.pause();
    } catch {
      /* flv.js may already be destroyed */
    }
    try {
      player.unload();
    } catch {
      /* ignore */
    }
    try {
      player.detachMediaElement();
    } catch {
      /* ignore */
    }
    try {
      player.destroy();
    } catch {
      /* ignore */
    }
  }
  if (!video) return;
  video.pause();
  video.removeAttribute('src');
  try {
    video.load();
  } catch {
    /* jsdom lacks HTMLMediaElement.load */
  }
}
