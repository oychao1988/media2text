import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiGet } from '../../lib/api';
import { showToast } from '../../lib/toast';
import { useCreators } from '../creators/CreatorsContext';
import { useLayoutStore } from '../layout/useLayoutStore';
import {
  LIVE_TRANSCRIPT_SELECTION,
  selectionFromSessionRow,
  type SessionListItem,
  type TranscriptSelection,
} from './transcriptSelection';

type SessionsResponse = {
  ok: boolean;
  sessions: SessionListItem[];
  active_session_id?: string | null;
};

function selectionKey(sel: TranscriptSelection): string {
  if (sel.mode === 'live') return 'live';
  return `${sel.kind}:${sel.itemId}`;
}

function rowLabel(row: SessionListItem): string {
  const base = row.display_label || row.title || row.item_id;
  if (row.kind === 'vod') return `${base} · 作品`;
  return `${base} · 直播`;
}

function liveCurrentLabel(isLive: boolean): string {
  return isLive ? '当前 · 录制中' : '当前 · 等待录制';
}

export function TranscriptSessionSelect() {
  const { selectedId, selected } = useCreators();
  const { transcriptSelection, setTranscriptSelection } = useLayoutStore();
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!selectedId) {
      setSessions([]);
      setTranscriptSelection(LIVE_TRANSCRIPT_SELECTION);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const res = await apiGet<SessionsResponse>(
          `/api/creators/${selectedId}/sessions`,
          true,
        );
        if (cancelled) return;
        setSessions(res.sessions ?? []);
        setTranscriptSelection(LIVE_TRANSCRIPT_SELECTION);
      } catch {
        if (!cancelled) setSessions([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId, setTranscriptSelection]);

  const activeSessionId = selected?.active_session_id ?? null;
  const isLiveNow = Boolean(selected?.is_live || selected?.status_light === 'green');

  const options = useMemo(() => {
    const rows: { key: string; label: string; selection: TranscriptSelection; hasTranscript: boolean }[] =
      [];
    rows.push({
      key: 'live',
      label: liveCurrentLabel(isLiveNow && Boolean(activeSessionId)),
      selection: LIVE_TRANSCRIPT_SELECTION,
      hasTranscript: true,
    });
    for (const row of sessions) {
      if (row.kind === 'live' && row.item_id === activeSessionId) continue;
      rows.push({
        key: selectionKey(selectionFromSessionRow(row)),
        label: rowLabel(row),
        selection: selectionFromSessionRow(row),
        hasTranscript: row.has_transcript,
      });
    }
    return rows;
  }, [activeSessionId, isLiveNow, sessions]);

  const currentKey = selectionKey(transcriptSelection);

  const onChange = useCallback(
    (key: string) => {
      const opt = options.find((o) => o.key === key);
      if (!opt) return;
      if (!opt.hasTranscript && opt.selection.mode === 'history') {
        showToast('该场次暂无转写', 'info');
        return;
      }
      setTranscriptSelection(opt.selection);
    },
    [options, setTranscriptSelection],
  );

  if (!selectedId) return null;

  return (
    <label className="transcript-session-wrap" title="历史场次">
      <select
        id="transcript-session-select"
        className="transcript-session-select"
        aria-label="选择历史场次"
        disabled={loading}
        value={options.some((o) => o.key === currentKey) ? currentKey : 'live'}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((opt) => (
          <option key={opt.key} value={opt.key}>
            {opt.label}
            {!opt.hasTranscript && opt.selection.mode === 'history' ? '（无转写）' : ''}
          </option>
        ))}
      </select>
    </label>
  );
}
