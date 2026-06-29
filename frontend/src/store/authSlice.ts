import { createSlice, type PayloadAction } from '@reduxjs/toolkit';
import type { User } from '../types/user';

interface AuthState {
  token: string | null;
  user:  User | null;
}

function loadFromStorage(): AuthState {
  try {
    return {
      token: localStorage.getItem('token'),
      user:  JSON.parse(localStorage.getItem('user') ?? 'null') as User | null,
    };
  } catch {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    return { token: null, user: null };
  }
}

const authSlice = createSlice({
  name: 'auth',
  initialState: loadFromStorage(),
  reducers: {
    setCredentials(state, action: PayloadAction<{ token: string; user: User }>) {
      state.token = action.payload.token;
      state.user  = action.payload.user;
      localStorage.setItem('token', action.payload.token);
      localStorage.setItem('user',  JSON.stringify(action.payload.user));
    },
    logout(state) {
      state.token = null;
      state.user  = null;
      localStorage.removeItem('token');
      localStorage.removeItem('user');
    },
  },
});

export const { setCredentials, logout } = authSlice.actions;
export default authSlice.reducer;
