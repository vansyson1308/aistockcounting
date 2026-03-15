import { describe, expect, it } from 'vitest';
import { sanitizeText } from '@/lib/sanitize';

describe('sanitizeText', () => {
  it('strips dangerous characters', () => {
    expect(sanitizeText('<script>alert(1)</script>')).toBe('scriptalert(1)/script');
    expect(sanitizeText('hello{world}$test')).toBe('helloworldtest');
    expect(sanitizeText('back\\slash')).toBe('backslash');
  });

  it('respects max length', () => {
    const long = 'a'.repeat(200);
    expect(sanitizeText(long, 50)).toHaveLength(50);
    expect(sanitizeText(long)).toHaveLength(100); // default max
  });

  it('handles empty and whitespace input', () => {
    expect(sanitizeText('')).toBe('');
    expect(sanitizeText('   ')).toBe('');
    expect(sanitizeText('  hello  ')).toBe('hello');
  });
});
