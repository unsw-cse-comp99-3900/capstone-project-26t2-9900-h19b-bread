const SESSION_EXPIRED_NOTICE_KEY = 'auth:session-expired';

export function markSessionExpired(): void {
  try {
    sessionStorage.setItem(SESSION_EXPIRED_NOTICE_KEY, 'true');
  } catch {
    // The redirect still needs to happen when browser storage is unavailable.
  }
}

export function consumeSessionExpiredNotice(): boolean {
  try {
    const expired = sessionStorage.getItem(SESSION_EXPIRED_NOTICE_KEY) === 'true';
    sessionStorage.removeItem(SESSION_EXPIRED_NOTICE_KEY);
    return expired;
  } catch {
    return false;
  }
}
