export function shouldNotifyCreatorMismatch(
  threadCreatorId: string,
  selectedCreatorId: string | null,
): boolean {
  return Boolean(selectedCreatorId && threadCreatorId !== selectedCreatorId);
}
