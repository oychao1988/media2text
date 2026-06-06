export type TranscriptSelection =
  | { mode: 'live' }
  | { mode: 'history'; kind: 'live' | 'vod'; itemId: string };

export type SessionListItem = {
  kind: 'live' | 'vod';
  item_id: string;
  has_transcript: boolean;
  has_summary?: boolean;
  display_label?: string | null;
  transcript_path?: string | null;
  summary_path?: string | null;
};

export const LIVE_TRANSCRIPT_SELECTION: TranscriptSelection = { mode: 'live' };

export function selectionFromSessionRow(row: SessionListItem): TranscriptSelection {
  return {
    mode: 'history',
    kind: row.kind,
    itemId: row.item_id,
  };
}
