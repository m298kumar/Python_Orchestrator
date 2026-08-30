import { describe, expect, it } from 'vitest';
import { formatDuration } from './Metrics';

describe('formatDuration', () => {
  it('keeps durations below one minute in seconds', () => {
    expect(formatDuration(12.34)).toBe('12.3s');
  });

  it('uses minutes and seconds at one minute or more', () => {
    expect(formatDuration(506.715)).toBe('8m 27s');
    expect(formatDuration(60)).toBe('1m 00s');
  });
});
