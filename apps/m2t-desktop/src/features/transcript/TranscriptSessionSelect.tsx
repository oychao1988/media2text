import { useCallback, useEffect, useMemo, useState } from 'react';
import { M2tSelect } from '../../components/M2tSelect';
import { apiGet } from '../../lib/api';
import { showToast } from '../../lib/toast';
import { useCreators } from '../creators/CreatorsContext';
import { useLayoutStore } from '../layout/useLayoutStore';
import {
  formatSessionOptionMeta,
  sessionOptionTitle,
} from './transcriptSessionFormat';
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

function liveCurrentLabel(isLive: boolean): string {
  return isLive ? '当前 · 录制中' : '当前 · 等待录制';
}

/** Survives TranscriptPane remounts so history picks are not reset to live. */
let lastSessionsCreatorId: string | null = null;

export function TranscriptSessionSelect() {
  const { selectedId, selected } = useCreators();
  const { transcriptSelection, setTranscriptSelection } = useLayoutStore();
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!selectedId) {
      lastSessionsCreatorId = null;
      setSessions([]);
      setTranscriptSelection(LIVE_TRANSCRIPT_SELECTION);
      return;
    }

    const creatorChanged = lastSessionsCreatorId !== selectedId;
    lastSessionsCreatorId = selectedId;
    if (creatorChanged) {
      setTranscriptSelection(LIVE_TRANSCRIPT_SELECTION);
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
    const rows: {
      key: string;
      label: string;
      selection: TranscriptSelection;
      hasTranscript: boolean;
      iconKind: 'live-current' | 'live' | 'vod';
      meta?: string;
      badge?: string;
    }[] = [];
    rows.push({
      key: 'live',
      label: liveCurrentLabel(isLiveNow && Boolean(activeSessionId)),
      selection: LIVE_TRANSCRIPT_SELECTION,
      hasTranscript: true,
      iconKind: 'live-current',
      meta: '实时',
    });
    for (const row of sessions) {
      if (row.kind === 'live' && row.item_id === activeSessionId) continue;
      const hasTranscript = row.has_transcript;
      rows.push({
        key: selectionKey(selectionFromSessionRow(row)),
        label: sessionOptionTitle(row),
        selection: selectionFromSessionRow(row),
        hasTranscript,
        iconKind: row.kind === 'vod' ? 'vod' : 'live',
        meta: formatSessionOptionMeta(row.started_at),
        badge: !hasTranscript ? '无转写' : undefined,
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
      }
      setTranscriptSelection(opt.selection);
    },
    [options, setTranscriptSelection],
  );

  if (!selectedId) return null;

  return (
    <div className="transcript-session-wrap" title="历史场次">
      <M2tSelect
        id="transcript-session-select"
        className="transcript-session-select m2t-select m2t-select--compact"
        ariaLabel="选择历史场次"
        disabled={loading}
        menuMinWidth={320}
        value={options.some((o) => o.key === currentKey) ? currentKey : 'live'}
        options={options.map((opt) => ({
          value: opt.key,
          label: opt.label,
          iconKind: opt.iconKind,
          meta: opt.meta,
          badge: opt.badge,
        }))}
        onChange={onChange}
      />
    </div>
  );
}
