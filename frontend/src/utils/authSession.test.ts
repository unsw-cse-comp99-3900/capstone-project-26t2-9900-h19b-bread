import { beforeEach, describe, expect, it } from 'vitest';

import { consumeSessionExpiredNotice, markSessionExpired } from './authSession';


describe('session expiry notice', () => {
  beforeEach(() => sessionStorage.clear());

  it('is consumed exactly once', () => {
    markSessionExpired();

    expect(consumeSessionExpiredNotice()).toBe(true);
    expect(consumeSessionExpiredNotice()).toBe(false);
  });

  it('does not report expiry when no marker exists', () => {
    expect(consumeSessionExpiredNotice()).toBe(false);
  });
});
