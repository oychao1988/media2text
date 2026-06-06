type IconProps = { className?: string };

export function IconRetry({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true" className={className}>
      <path d="M21 12a9 9 0 1 1-2.64-6.36" />
      <path d="M21 3v6h-6" />
    </svg>
  );
}

export function IconEdit({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true" className={className}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}

export function IconCopy({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true" className={className}>
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

export function IconThumbUp({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true" className={className}>
      <path d="M7 10v12" />
      <path d="M15 5.9c-.7-.7-1.8-.7-2.5 0l-1.8 1.8a2 2 0 0 0-.6 1.4V20h6.8a2 2 0 0 0 2-1.7l.6-7.1a2 2 0 0 0-2-2.2H15Z" />
    </svg>
  );
}

export function IconThumbDown({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true" className={className}>
      <path d="M17 14V2" />
      <path d="M9 18.1c.7.7 1.8.7 2.5 0l1.8-1.8a2 2 0 0 0 .6-1.4V4H7.3a2 2 0 0 0-2 1.7l-.6 7.1a2 2 0 0 0 2 2.2H9Z" />
    </svg>
  );
}
