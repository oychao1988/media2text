import {
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import type { Creator } from '../../lib/types';
import { CreatorProfileSummary } from './CreatorProfileSummary';

const SHOW_DELAY_MS = 280;
const HIDE_DELAY_MS = 120;
const GAP_PX = 10;

type CreatorHoverPopoverProps = {
  creator: Creator;
  children: ReactNode;
  className?: string;
};

export function CreatorHoverPopover({ creator, children, className }: CreatorHoverPopoverProps) {
  const tooltipId = useId();
  const anchorRef = useRef<HTMLDivElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const showTimer = useRef<ReturnType<typeof setTimeout>>();
  const hideTimer = useRef<ReturnType<typeof setTimeout>>();
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0 });

  const clearTimers = useCallback(() => {
    clearTimeout(showTimer.current);
    clearTimeout(hideTimer.current);
  }, []);

  const updatePosition = useCallback(() => {
    const anchor = anchorRef.current;
    if (!anchor) return;
    const rect = anchor.getBoundingClientRect();
    setCoords({
      top: rect.top + rect.height / 2,
      left: rect.right + GAP_PX,
    });
  }, []);

  const scheduleShow = useCallback(() => {
    clearTimeout(hideTimer.current);
    if (open) return;
    clearTimeout(showTimer.current);
    showTimer.current = setTimeout(() => {
      updatePosition();
      setOpen(true);
    }, SHOW_DELAY_MS);
  }, [open, updatePosition]);

  const scheduleHide = useCallback(() => {
    clearTimeout(showTimer.current);
    clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => setOpen(false), HIDE_DELAY_MS);
  }, []);

  useEffect(() => () => clearTimers(), [clearTimers]);

  useLayoutEffect(() => {
    if (!open) return;
    const popover = popoverRef.current;
    if (!popover) return;
    const height = popover.offsetHeight;
    const minTop = 12 + height / 2;
    const maxBottom = window.innerHeight - 12 - height / 2;
    setCoords((prev) => ({
      ...prev,
      top: Math.min(Math.max(prev.top, minTop), maxBottom),
    }));
  }, [open, creator.id]);

  useEffect(() => {
    if (!open) return;
    const onScrollOrResize = () => updatePosition();
    window.addEventListener('scroll', onScrollOrResize, true);
    window.addEventListener('resize', onScrollOrResize);
    return () => {
      window.removeEventListener('scroll', onScrollOrResize, true);
      window.removeEventListener('resize', onScrollOrResize);
    };
  }, [open, updatePosition]);

  const anchorClass = ['creator-hover-anchor', className].filter(Boolean).join(' ');

  return (
    <>
      <div
        ref={anchorRef}
        className={anchorClass}
        onMouseEnter={scheduleShow}
        onMouseLeave={scheduleHide}
        onFocus={scheduleShow}
        onBlur={scheduleHide}
        aria-describedby={open ? tooltipId : undefined}
      >
        {children}
      </div>
      {open
        ? createPortal(
            <div
              ref={popoverRef}
              id={tooltipId}
              className="creator-hover-popover"
              style={{ top: coords.top, left: coords.left }}
              role="tooltip"
              onMouseEnter={scheduleShow}
              onMouseLeave={scheduleHide}
            >
              <div className="creator-hover-popover-inner creator-profile-summary">
                <CreatorProfileSummary creator={creator} showStatus avatarSize="lg" />
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
