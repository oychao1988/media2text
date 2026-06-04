import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const layoutCss = readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), '../../styles/layout.css'),
  'utf-8',
);

function narrowBlock(): string {
  const start = layoutCss.indexOf('@media (max-width: 768px)');
  expect(start).toBeGreaterThanOrEqual(0);
  return layoutCss.slice(start);
}

describe('responsive layout (≤768px)', () => {
  it('forces dual-rail grid columns', () => {
    const block = narrowBlock();
    expect(block).toContain('var(--sidebar-collapsed-w)');
    expect(block).toContain('var(--right-collapsed-w)');
    expect(block).toMatch(/grid-template-columns:[\s\S]*minmax\(0,\s*1fr\)/);
  });

  it('hides expanded panel content and column resize grips', () => {
    const block = narrowBlock();
    expect(block).toContain('.left-content');
    expect(block).toContain('.right-content');
    expect(block).toContain('.col-resize');
    expect(block).toMatch(/display:\s*none\s*!important/);
  });

  it('keeps left and right rails visible', () => {
    const block = narrowBlock();
    expect(block).toContain('.left-rail');
    expect(block).toContain('.right-rail');
    expect(block).toMatch(/\.left-rail[\s\S]*display:\s*flex/);
  });
});
