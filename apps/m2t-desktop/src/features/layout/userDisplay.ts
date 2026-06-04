/** Left rail + user bar display (prototype uses local user initial). */
export const USER_DISPLAY_NAME = '本地用户';

export function userDisplayInitial(): string {
  const n = USER_DISPLAY_NAME.trim();
  return n ? n.charAt(0) : '?';
}
