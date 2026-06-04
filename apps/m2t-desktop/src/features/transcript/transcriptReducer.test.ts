import { describe, expect, it } from 'vitest';
import { initialTranscriptState, transcriptReducer } from './transcriptReducer';

describe('transcriptReducer', () => {
  it('marks waiting when payload is empty', () => {
    const next = transcriptReducer(initialTranscriptState, {
      type: 'payload',
      payload: { partial: true, text: '', segments: [] },
    });
    expect(next.waiting).toBe(true);
    expect(next.partial).toBe(true);
  });

  it('fills text and clears waiting on content', () => {
    const next = transcriptReducer(initialTranscriptState, {
      type: 'payload',
      payload: {
        partial: true,
        text: 'hello',
        segments: [{ start: 0, end: 1, text: 'hello' }],
      },
    });
    expect(next.waiting).toBe(false);
    expect(next.text).toBe('hello');
    expect(next.segments).toHaveLength(1);
  });

  it('tracks disconnect banner', () => {
    const next = transcriptReducer(
      { ...initialTranscriptState, waiting: false, text: 'x' },
      { type: 'disconnected', value: true },
    );
    expect(next.disconnected).toBe(true);
  });

  it('resets on session change', () => {
    const next = transcriptReducer(
      { ...initialTranscriptState, text: 'old', waiting: false },
      { type: 'reset' },
    );
    expect(next).toEqual(initialTranscriptState);
  });
});
