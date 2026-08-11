import { beforeEach, describe, expect, it } from 'vitest';

import reducer, { logout, setCredentials } from './authSlice';


const user = {
  user_id: '5',
  enterprise_id: '7',
  email: 'publisher@example.test',
  role: 'PUBLISHER',
};

describe('auth state persistence', () => {
  beforeEach(() => localStorage.clear());

  it('stores credentials when login succeeds', () => {
    const state = reducer(
      { token: null, user: null },
      setCredentials({ token: 'jwt-token', user }),
    );

    expect(state).toEqual({ token: 'jwt-token', user });
    expect(localStorage.getItem('token')).toBe('jwt-token');
    expect(JSON.parse(localStorage.getItem('user') ?? 'null')).toEqual(user);
  });

  it('clears state and storage on logout', () => {
    localStorage.setItem('token', 'jwt-token');
    localStorage.setItem('user', JSON.stringify(user));

    const state = reducer({ token: 'jwt-token', user }, logout());

    expect(state).toEqual({ token: null, user: null });
    expect(localStorage.getItem('token')).toBeNull();
    expect(localStorage.getItem('user')).toBeNull();
  });
});
