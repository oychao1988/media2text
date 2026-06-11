import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { LiveSessionSummary } from '../../lib/types';
import { ViewPlayback } from './ViewPlayback';

const mockHlsInstances: Array<{ loadSource: ReturnType<typeof vi.fn>; attachMedia: ReturnType<typeof vi.fn>; on: ReturnType<typeof vi.fn>; destroy: ReturnType<typeof vi.fn> }> = [];

vi.mock('hls.js', () => {
  class MockHls {
    static isSupported = vi.fn(() => true);
    static Events = { ERROR: 'hlsError' };
    loadSource = vi.fn();
    attachMedia = vi.fn();
    on = vi.fn();
    destroy = vi.fn();
    constructor() {
      mockHlsInstances.push(this);
    }
  }
  return { default: MockHls };
});

vi.mock('flv.js', () => ({
  default: {
    isSupported: vi.fn(() => false),
    createPlayer: vi.fn(),
    Events: { ERROR: 'error' },
  },
}));

vi.mock('../../lib/api', () => ({
  listGalleryImages: vi.fn(),
  mediaUrl: vi.fn(async (p: string) => `http://api.test/media?path=${encodeURIComponent(p)}`),
  playbackM3u8Url: vi.fn(async (id: string) => `http://api.test/api/sessions/${id}/playback.m3u8`),
  playbackMp4Url: vi.fn(async (id: string) => `http://api.test/api/sessions/${id}/playback.mp4`),
}));

vi.mock('../layout/useLayoutStore', () => ({
  useLayoutStore: () => ({ backToHistory: vi.fn() }),
}));

const baseSession = (overrides: Partial<LiveSessionSummary> = {}): LiveSessionSummary => ({
  kind: 'live',
  item_id: 'sess-1',
  session_id: 'sess-1',
  aweme_id: null,
  title: null,
  creator_id: 'c1',
  started_at: '2026-06-09T12:00:00Z',
  ended_at: '2026-06-09T13:00:00Z',
  status: 'completed',
  local_path: 'creators/sec/live/sess-dir',
  temp_path: 'creators/sec/live/sess-dir/master.m3u8',
  media_path: 'creators/sec/live/sess-dir/master.m3u8',
  pipeline_mode: 'streaming',
  transcribe_status: 'completed',
  cloud_upload_status: null,
  cloud_file_id: null,
  cloud_relative_path: null,
  cloud_available: false,
  has_transcript: true,
  has_summary: false,
  media_available: true,
  transcript_path: 'creators/sec/live/sess-dir/anchor.transcript.json',
  summary_path: null,
  ...overrides,
});

describe('ViewPlayback hls.js', () => {
  beforeEach(() => {
    mockHlsInstances.length = 0;
    vi.clearAllMocks();
  });

  it('uses playback.m3u8 for media_format=hls', async () => {
    const onTimeUpdate = vi.fn();
    const { playbackM3u8Url } = await import('../../lib/api');
    render(
      <ViewPlayback
        active
        creatorName="主播"
        session={baseSession({ media_format: 'hls' })}
        onTimeUpdate={onTimeUpdate}
      />,
    );

    await waitFor(() => {
      expect(playbackM3u8Url).toHaveBeenCalledWith('sess-1');
      expect(mockHlsInstances.length).toBeGreaterThan(0);
    });
    expect(mockHlsInstances[0].loadSource).toHaveBeenCalledWith(
      'http://api.test/api/sessions/sess-1/playback.m3u8',
    );
  });

  it('attempts hls playback for cloud-only sessions without crashing', async () => {
    const { playbackM3u8Url } = await import('../../lib/api');
    render(
      <ViewPlayback
        active
        creatorName="主播"
        session={baseSession({
          media_format: 'hls',
          media_available: false,
          cloud_available: true,
          cloud_upload_status: 'done',
          cloud_file_id: 'cf-1',
        })}
      />,
    );
    await waitFor(() => {
      expect(playbackM3u8Url).toHaveBeenCalledWith('sess-1');
    });
    expect(document.querySelector('video')).toBeTruthy();
  });

  it('uses playback.m3u8 when discontinuity_at is present', async () => {
    const { playbackM3u8Url, playbackMp4Url } = await import('../../lib/api');
    render(
      <ViewPlayback
        active
        creatorName="主播"
        session={baseSession({ media_format: 'hls', discontinuity_at: [630.76] })}
      />,
    );
    await waitFor(() => {
      expect(playbackM3u8Url).toHaveBeenCalledWith('sess-1');
    });
    expect(playbackMp4Url).not.toHaveBeenCalled();
    expect(mockHlsInstances.length).toBeGreaterThan(0);
    expect(document.querySelector('video')).toBeTruthy();
  });

  it('shows cloud fallback hint when hls fails on cloud-only session', async () => {
    const { playbackM3u8Url } = await import('../../lib/api');
    vi.mocked(playbackM3u8Url).mockRejectedValueOnce(new Error('network'));
    render(
      <ViewPlayback
        active
        creatorName="主播"
        session={baseSession({
          media_format: 'hls',
          media_available: false,
          cloud_available: true,
        })}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText(/云端分段不可用/)).toBeInTheDocument();
    });
  });
});
