/** Regions that keep native text selection and context menu (right sidebar + form fields). */
const TEXT_INTERACTION =
  'input, textarea, select, [contenteditable="true"], .transcript-body, .agent-chat-md, .agent-composer';

function isTextInteractionTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return Boolean(target.closest(TEXT_INTERACTION));
}

/** Disable rubber-band selection on app chrome; preserve text UX in inputs and right panel. */
export function installDesktopInputGuards(): () => void {
  const onContextMenu = (event: MouseEvent) => {
    if (isTextInteractionTarget(event.target)) return;
    event.preventDefault();
  };

  const onSelectStart = (event: Event) => {
    if (!isTextInteractionTarget(event.target)) event.preventDefault();
  };

  const onDragStart = (event: DragEvent) => {
    if (!isTextInteractionTarget(event.target)) event.preventDefault();
  };

  document.addEventListener('contextmenu', onContextMenu);
  document.addEventListener('selectstart', onSelectStart);
  document.addEventListener('dragstart', onDragStart);

  return () => {
    document.removeEventListener('contextmenu', onContextMenu);
    document.removeEventListener('selectstart', onSelectStart);
    document.removeEventListener('dragstart', onDragStart);
  };
}
