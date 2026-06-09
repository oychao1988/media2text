import { describe, expect, it } from 'vitest';
import { alignPlaybackTime, sessionUsesHls } from './playbackTime';

describe('alignPlaybackTime', () => {
  it('returns media time when no discontinuities', () => {
    expect(alignPlaybackTime(42.5, undefined)).toBe(42.5);
    expect(alignPlaybackTime(42.5, [])).toBe(42.5);
  });

  it('keeps continuous HLS media time across discontinuity markers', () => {
    expect(alignPlaybackTime(100, [120])).toBe(100);
    expect(alignPlaybackTime(130, [120])).toBe(130);
  });
});

describe('sessionUsesHls', () => {
  it('detects hls by media_format or m3u8 path', () => {
    expect(sessionUsesHls({ media_format: 'hls' })).toBe(true);
    expect(sessionUsesHls({ media_path: 'creators/x/live/s/master.m3u8' })).toBe(true);
    expect(sessionUsesHls({ media_path: 'creators/x/live/s/file.flv' })).toBe(false);
  });
});
