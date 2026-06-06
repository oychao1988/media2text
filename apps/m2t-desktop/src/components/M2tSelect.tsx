import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';

export type M2tSelectIconKind = 'live-current' | 'live' | 'vod';

export type M2tSelectOption = {
  value: string;
  label: string;
  disabled?: boolean;
  iconKind?: M2tSelectIconKind;
  meta?: string;
  badge?: string;
};

type Props = {
  id?: string;
  value: string;
  options: M2tSelectOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  ariaLabel: string;
  className?: string;
  title?: string;
  menuMinWidth?: number;
  /** Prefer opening above the trigger (e.g. bottom composer). */
  preferPlacement?: 'auto' | 'above' | 'below';
};

const MENU_GAP = 4;
const MAX_MENU_HEIGHT = 480;

function SelectOptionIcon({ kind }: { kind?: M2tSelectIconKind }) {
  if (!kind) return null;
  if (kind === 'live-current') {
    return (
      <span className="m2t-select-option-icon kind-live-current" aria-hidden="true">
        <span className="m2t-select-icon-dot" />
      </span>
    );
  }
  if (kind === 'live') {
    return (
      <span className="m2t-select-option-icon kind-live" aria-hidden="true">
        <svg viewBox="0 0 16 16" width="12" height="12" focusable="false">
          <circle cx="8" cy="8" r="4" fill="currentColor" />
        </svg>
      </span>
    );
  }
  return (
    <span className="m2t-select-option-icon kind-vod" aria-hidden="true">
      <svg viewBox="0 0 16 16" width="12" height="12" focusable="false">
        <path
          d="M3.5 2.5h9a1 1 0 011 1v9a1 1 0 01-1 1h-9a1 1 0 01-1-1v-9a1 1 0 011-1zm1.5 2.2v5.6l4.8-2.8-4.8-2.8z"
          fill="currentColor"
        />
      </svg>
    </span>
  );
}

function computeMenuStyle(
  trigger: HTMLElement,
  menuMinWidth = 0,
  preferPlacement: 'auto' | 'above' | 'below' = 'auto',
): CSSProperties {
  const rect = trigger.getBoundingClientRect();
  const maxH = Math.min(MAX_MENU_HEIGHT, window.innerHeight - 16);
  const spaceBelow = window.innerHeight - rect.bottom - MENU_GAP - 8;
  const spaceAbove = rect.top - MENU_GAP - 8;
  const openDown =
    preferPlacement === 'below'
      ? true
      : preferPlacement === 'above'
        ? false
        : spaceBelow >= Math.min(160, maxH) || spaceBelow >= spaceAbove;
  const maxWidth = Math.min(420, window.innerWidth - 16);
  const minWidth = Math.max(rect.width, menuMinWidth);

  if (openDown) {
    return {
      position: 'fixed',
      top: rect.bottom + MENU_GAP,
      left: Math.min(rect.left, window.innerWidth - maxWidth - 8),
      minWidth,
      maxWidth,
      maxHeight: Math.min(maxH, Math.max(120, spaceBelow)),
    };
  }

  const menuHeight = Math.min(maxH, Math.max(120, spaceAbove));
  return {
    position: 'fixed',
    bottom: window.innerHeight - rect.top + MENU_GAP,
    left: Math.min(rect.left, window.innerWidth - maxWidth - 8),
    minWidth,
    maxWidth,
    maxHeight: menuHeight,
  };
}

function renderOptionContent(opt: M2tSelectOption): ReactNode {
  return (
    <>
      <SelectOptionIcon kind={opt.iconKind} />
      <span className="m2t-select-option-body">
        <span className="m2t-select-option-label">{opt.label}</span>
        {opt.badge ? <span className="m2t-select-option-badge">{opt.badge}</span> : null}
      </span>
      {opt.meta ? <span className="m2t-select-option-meta">{opt.meta}</span> : null}
    </>
  );
}

export function M2tSelect({
  id,
  value,
  options,
  onChange,
  disabled = false,
  ariaLabel,
  className = 'm2t-select',
  title,
  menuMinWidth = 0,
  preferPlacement = 'auto',
}: Props) {
  const listId = useId();
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});

  const selected = options.find((o) => o.value === value) ?? options[0];

  const close = useCallback(() => setOpen(false), []);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) {
      setMenuStyle({});
      return;
    }

    let raf = 0;
    const update = () => {
      if (!triggerRef.current) return;
      setMenuStyle(computeMenuStyle(triggerRef.current, menuMinWidth, preferPlacement));
    };
    const schedule = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(update);
    };

    schedule();
    window.addEventListener('resize', schedule);
    window.addEventListener('scroll', schedule, true);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', schedule);
      window.removeEventListener('scroll', schedule, true);
    };
  }, [menuMinWidth, open, options.length, preferPlacement]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const target = e.target as Node;
      if (wrapRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [close, open]);

  const pick = (next: string, optionDisabled?: boolean) => {
    if (optionDisabled || disabled) return;
    onChange(next);
    close();
  };

  const menu =
    open && !disabled ? (
      <ul
        ref={menuRef}
        className="m2t-select-menu"
        id={listId}
        role="listbox"
        aria-label={ariaLabel}
        style={menuStyle}
      >
        {options.map((opt) => {
          const isSelected = opt.value === value;
          return (
            <li key={opt.value} role="presentation">
              <button
                type="button"
                role="option"
                aria-selected={isSelected}
                className={['m2t-select-option', isSelected ? 'selected' : ''].filter(Boolean).join(' ')}
                disabled={opt.disabled}
                onClick={() => pick(opt.value, opt.disabled)}
              >
                {renderOptionContent(opt)}
              </button>
            </li>
          );
        })}
      </ul>
    ) : null;

  return (
    <div ref={wrapRef} className="m2t-select-wrap">
      <button
        ref={triggerRef}
        type="button"
        id={id}
        className={`m2t-select-trigger ${className}`.trim()}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        disabled={disabled}
        title={title}
        onClick={() => {
          if (disabled) return;
          setOpen((v) => !v);
        }}
      >
        <span className="m2t-select-value">{selected?.label ?? value}</span>
      </button>
      {menu ? createPortal(menu, document.body) : null}
    </div>
  );
}
