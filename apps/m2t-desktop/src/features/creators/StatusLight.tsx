import type { StatusLight as StatusLightKind } from '../../lib/types';
import { statusAriaLabel } from './creatorUtils';

type Props = {
  light: StatusLightKind;
  abbr?: string;
  className?: string;
};

export function StatusLight({ light, abbr, className = '' }: Props) {
  const label = statusAriaLabel(light);
  const short = abbr ?? label.charAt(0);
  return (
    <span
      className={`light ${light}${className ? ` ${className}` : ''}`}
      data-abbr={short}
      title={label}
      aria-label={label}
      role="img"
    />
  );
}
