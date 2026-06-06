export function shouldNotifyCreatorMismatch(
  threadCreatorId: string | null | undefined,
  selectedCreatorId: string | null,
): boolean {
  if (!threadCreatorId) return false;
  return Boolean(selectedCreatorId && threadCreatorId !== selectedCreatorId);
}

/** Block send when a creator-scoped thread is open but sidebar points elsewhere. */
export function isComposerBlocked(
  threadCreatorId: string | null | undefined,
  selectedCreatorId: string | null,
): boolean {
  if (!threadCreatorId) return false;
  if (!selectedCreatorId) return true;
  return threadCreatorId !== selectedCreatorId;
}

export function isGlobalThread(threadCreatorId: string | null | undefined): boolean {
  return threadCreatorId == null || threadCreatorId === '';
}
