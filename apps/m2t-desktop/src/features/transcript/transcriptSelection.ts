export type TranscriptSelection =
  | { mode: 'live' }
  | {
      mode: 'history';
      kind: 'live' | 'vod';
      itemId: string;
      hasTranscript: boolean;
      hasSummary: boolean;
      transcriptPath?: string | null;
      summaryPath?: string | null;
    };

export type SessionListItem = {
  kind: 'live' | 'vod';
  item_id: string;
  has_transcript: boolean;
  has_summary?: boolean;
  display_label?: string | null;
  title?: string | null;
  started_at?: string | null;
  transcript_path?: string | null;
  summary_path?: string | null;
};

export const LIVE_TRANSCRIPT_SELECTION: TranscriptSelection = { mode: 'live' };

export function selectionFromSessionRow(row: SessionListItem): TranscriptSelection {
  return {
    mode: 'history',
    kind: row.kind,
    itemId: row.item_id,
    hasTranscript: row.has_transcript,
    hasSummary: Boolean(row.has_summary),
    transcriptPath: row.transcript_path ?? null,
    summaryPath: row.summary_path ?? null,
  };
}
