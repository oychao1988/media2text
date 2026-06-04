import type { TranscriptPayload, TranscriptSegment } from '../../lib/types';

export type TranscriptViewState = {
  loading: boolean;
  disconnected: boolean;
  waiting: boolean;
  partial: boolean;
  text: string;
  segments: TranscriptSegment[];
  markdown: string | null;
};

export type TranscriptAction =
  | { type: 'reset' }
  | { type: 'loading' }
  | { type: 'disconnected'; value: boolean }
  | { type: 'payload'; payload: TranscriptPayload }
  | { type: 'waiting'; value: boolean };

export const initialTranscriptState: TranscriptViewState = {
  loading: true,
  disconnected: false,
  waiting: true,
  partial: false,
  text: '',
  segments: [],
  markdown: null,
};

export function transcriptReducer(
  state: TranscriptViewState,
  action: TranscriptAction,
): TranscriptViewState {
  switch (action.type) {
    case 'reset':
      return { ...initialTranscriptState };
    case 'loading':
      return { ...state, loading: true };
    case 'disconnected':
      return { ...state, disconnected: action.value };
    case 'waiting':
      return { ...state, waiting: action.value, loading: false };
    case 'payload': {
      const p = action.payload;
      const text = p.text ?? p.markdown ?? '';
      const segments = p.segments ?? [];
      const hasContent = Boolean(text.trim() || segments.length);
      return {
        loading: false,
        disconnected: false,
        waiting: !hasContent,
        partial: Boolean(p.partial),
        text,
        segments,
        markdown: p.markdown ?? null,
      };
    }
    default:
      return state;
  }
}

export function formatTs(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  }
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}
