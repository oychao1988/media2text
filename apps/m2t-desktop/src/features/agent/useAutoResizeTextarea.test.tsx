/** @vitest-environment jsdom */
import { render } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { useAutoResizeTextarea } from './useAutoResizeTextarea';

function TextareaHarness() {
  const [value, setValue] = useState('');
  const { ref, onInput } = useAutoResizeTextarea(value, 10);
  return (
    <textarea
      ref={ref}
      className="agent-composer-input"
      value={value}
      rows={1}
      onChange={(e) => setValue(e.target.value)}
      onInput={onInput}
    />
  );
}

describe('useAutoResizeTextarea', () => {
  it('does not set inline height on mount when empty', () => {
    const { container } = render(<TextareaHarness />);
    const el = container.querySelector('textarea')!;
    expect(el.style.height).toBe('');
  });
});
