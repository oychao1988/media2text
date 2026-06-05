import { describe, expect, it } from 'vitest';
import {
  needsEnvironmentRepair,
  type DoctorCheck,
} from './bootstrapHealth';

describe('needsEnvironmentRepair', () => {
  it('returns true when ffmpeg or playwright_browser missing', () => {
    const checks: DoctorCheck[] = [
      { name: 'ffmpeg', ok: false },
      { name: 'playwright_browser', ok: true },
    ];
    expect(needsEnvironmentRepair(checks)).toBe(true);
  });

  it('returns false when required checks pass', () => {
    const checks: DoctorCheck[] = [
      { name: 'ffmpeg', ok: true },
      { name: 'playwright_browser', ok: true },
      { name: 'session_douyin', ok: false },
    ];
    expect(needsEnvironmentRepair(checks)).toBe(false);
  });
});
