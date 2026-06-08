import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { showToast } from '../../lib/toast';
import {
  attachmentsFromSessionOffer,
  dedupeByPath,
  legacyBindingToAttachments,
} from './agentAttachments';
import type { ContextAttachment, ContextMode, SessionDocumentsOffer } from './contextAttachment';

type TabAttachmentsMap = Record<string, ContextAttachment[]>;

export function useAgentAttachments(opts: {
  activeTabKey: string | null;
  activeThreadId: string | null;
  threadCreatorId: string | null;
  creatorName: string;
  sessionId: string | null;
  sessionKind: 'live' | 'vod' | null;
  contextMode: ContextMode;
  legacyTranscriptPath?: string | null;
  legacySummaryPath?: string | null;
  legacyAttachments?: ContextAttachment[] | null;
}) {
  const [byTab, setByTab] = useState<TabAttachmentsMap>({});
  const lastOfferKeyRef = useRef<string | null>(null);

  useEffect(() => {
    lastOfferKeyRef.current = null;
  }, [opts.activeTabKey]);

  const activeAttachments = useMemo(() => {
    if (!opts.activeTabKey) return [];
    return byTab[opts.activeTabKey] ?? [];
  }, [byTab, opts.activeTabKey]);

  const hydrateThreadTab = useCallback(
    (tabKey: string) => {
      const legacy = legacyBindingToAttachments({
        attachments: opts.legacyAttachments,
        transcriptPath: opts.legacyTranscriptPath,
        summaryPath: opts.legacySummaryPath,
        creatorId: opts.threadCreatorId ?? '',
        creatorName: opts.creatorName,
        sessionKind: opts.sessionKind,
        itemId: opts.sessionId ?? '',
      });
      if (!legacy.length) return;
      setByTab((prev) => {
        if (prev[tabKey]?.length) return prev;
        return { ...prev, [tabKey]: legacy };
      });
    },
    [
      opts.creatorName,
      opts.legacyAttachments,
      opts.legacySummaryPath,
      opts.legacyTranscriptPath,
      opts.sessionId,
      opts.sessionKind,
      opts.threadCreatorId,
    ],
  );

  useEffect(() => {
    if (!opts.activeTabKey || !opts.activeThreadId) return;
    hydrateThreadTab(opts.activeTabKey);
  }, [hydrateThreadTab, opts.activeTabKey, opts.activeThreadId]);

  const appendSessionAttachments = useCallback(
    (offer: SessionDocumentsOffer) => {
      if (!opts.activeTabKey) return;
      const offerKey = `${offer.sessionId}:${offer.transcriptPath ?? ''}:${offer.summaryPath ?? ''}`;
      if (lastOfferKeyRef.current === offerKey) return;
      lastOfferKeyRef.current = offerKey;

      const built = attachmentsFromSessionOffer(offer);
      if (!built.length) {
        if (!offer.hasTranscript && !offer.hasSummary) {
          showToast('该场次暂无转写', 'info');
        } else if (!offer.hasTranscript) {
          showToast('该场次暂无转写', 'info');
        }
        return;
      }

      setByTab((prev) => {
        const current = prev[opts.activeTabKey!] ?? [];
        const merged = dedupeByPath([...current, ...built]);
        return { ...prev, [opts.activeTabKey!]: merged };
      });
    },
    [opts.activeTabKey],
  );

  const removeAttachment = useCallback(
    (id: string) => {
      if (!opts.activeTabKey) return;
      setByTab((prev) => {
        const current = prev[opts.activeTabKey!] ?? [];
        const next = current.filter((a) => a.id !== id);
        return { ...prev, [opts.activeTabKey!]: next };
      });
    },
    [opts.activeTabKey],
  );

  const appendMentionAttachment = useCallback(
    (attachment: ContextAttachment) => {
      if (!opts.activeTabKey) return;
      setByTab((prev) => {
        const current = prev[opts.activeTabKey!] ?? [];
        const merged = dedupeByPath([...current, attachment]);
        return { ...prev, [opts.activeTabKey!]: merged };
      });
    },
    [opts.activeTabKey],
  );

  const clearTab = useCallback((tabKey: string) => {
    setByTab((prev) => {
      if (!(tabKey in prev)) return prev;
      const { [tabKey]: _removed, ...rest } = prev;
      return rest;
    });
    if (lastOfferKeyRef.current) lastOfferKeyRef.current = null;
  }, []);

  const migrateTabAttachments = useCallback((fromKey: string, toKey: string) => {
    if (fromKey === toKey) return;
    setByTab((prev) => {
      const items = prev[fromKey];
      if (!items?.length) return prev;
      const { [fromKey]: _removed, ...rest } = prev;
      const existing = rest[toKey] ?? [];
      return { ...rest, [toKey]: dedupeByPath([...existing, ...items]) };
    });
  }, []);

  return {
    activeAttachments,
    appendSessionAttachments,
    appendMentionAttachment,
    removeAttachment,
    clearTab,
    migrateTabAttachments,
  };
}
