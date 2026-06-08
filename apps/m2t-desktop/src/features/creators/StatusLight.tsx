import type { StatusLight as StatusLightKind } from '../../lib/types';
import { statusAriaLabel } from './creatorUtils';

type Props = {
  light: StatusLightKind;
  abbr?: string;
  /** Overrides default aria/title when API sends a specific status_label. */
  label?: string;
  className?: string;
};

export function StatusLight({ light, abbr, label, className = '' }: Props) {
  const displayLabel = label ?? statusAriaLabel(light);
  const short = abbr ?? displayLabel.charAt(0);
  return (
    <span
      className={`light ${light}${className ? ` ${className}` : ''}`}
      data-abbr={short}
      title={displayLabel}
      aria-label={displayLabel}
      role="img"
    />
  );
}
