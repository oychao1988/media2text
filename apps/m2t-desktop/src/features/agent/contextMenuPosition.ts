const MENU_WIDTH = 148;
const MENU_HEIGHT = 88;
const VIEWPORT_PAD = 8;

export function positionAgentContextMenu(anchorRect: DOMRect): { x: number; y: number } {
  const maxX = window.innerWidth - MENU_WIDTH - VIEWPORT_PAD;
  const maxY = window.innerHeight - MENU_HEIGHT - VIEWPORT_PAD;
  const x = Math.max(VIEWPORT_PAD, Math.min(anchorRect.right - MENU_WIDTH, maxX));
  const y = Math.max(VIEWPORT_PAD, Math.min(anchorRect.bottom + 4, maxY));
  return { x, y };
}
