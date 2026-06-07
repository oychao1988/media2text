import { describe, expect, it } from 'vitest';
import { tavilyApiKeyForPatch } from './distillConfigPatch';

describe('tavilyApiKeyForPatch', () => {
  it('includes a newly entered api key', () => {
    expect(tavilyApiKeyForPatch('tvly-secret')).toBe('tvly-secret');
  });

  it('omits masked placeholder keys', () => {
    expect(tavilyApiKeyForPatch('***')).toBeUndefined();
  });

  it('omits empty values', () => {
    expect(tavilyApiKeyForPatch('')).toBeUndefined();
    expect(tavilyApiKeyForPatch(null)).toBeUndefined();
  });
});
