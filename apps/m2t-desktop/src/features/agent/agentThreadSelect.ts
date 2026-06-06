export function shouldNotifyCreatorMismatch(
  threadCreatorId: string | null | undefined,
  selectedCreatorId: string | null,
): boolean {
  if (!threadCreatorId) return false;
  return Boolean(selectedCreatorId && threadCreatorId !== selectedCreatorId);
}

export function isGlobalThread(threadCreatorId: string | null | undefined): boolean {
  return threadCreatorId == null || threadCreatorId === '';
}
